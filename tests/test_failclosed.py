import json
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from scholar.core.papers import Claim, Evidence, Paper
from scholar.jev.client import JevClient
from scholar.jev.gates import PostRAGVerifier
from scholar.mcp import server
from scholar.retrieval.engine import ScholarEngine


def _high_overlap_paper_and_claim() -> tuple[Paper, Evidence, Claim]:
    """Creates a paper/evidence/claim with high keyword overlap where heuristic scores high."""
    text = (
        "The proposed airtime scheduler reduces 99th percentile loaded latency by 68% "
        "on QCA988x physical hardware testbed."
    )
    paper = Paper(
        id="2401.9001",
        title="Loaded Latency Scheduler on QCA988x Hardware",
        abstract=text,
        categories=["cs.NI"],
    )
    evidence = Evidence(
        paper_id=paper.id,
        section="abstract",
        text=text,
        start_char=0,
        end_char=len(text),
        source_field="abstract",
        doc_id=paper.id,
    )
    claim = Claim(
        id="c_fc_1",
        statement="The proposed airtime scheduler reduces 99th percentile loaded latency by 68% on QCA988x hardware.",
        paper_id=paper.id,
    )
    return paper, evidence, claim


@pytest.mark.asyncio
async def test_failclosed_no_api_key_returns_unverified_and_marks_auxiliary_unreliable(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    paper, evidence, claim = _high_overlap_paper_and_claim()

    client = JevClient()
    verifier = PostRAGVerifier(client)
    checked = await verifier.verify_claim(claim, evidence)

    assert checked.status == "unverified"
    assert checked.status not in ("supported", "partial", "contradicted", "unsupported")
    assert checked.result_state == "unverified"
    assert checked.source == "unavailable"
    assert checked.verification_probability is None
    assert checked.contradiction_probability is None
    assert checked.failure_reason == "missing_api_key"
    assert checked.auxiliary_heuristic is not None
    assert checked.auxiliary_heuristic["reliable"] is False
    assert checked.auxiliary_heuristic["verification_probability"] > 0.70

    # End-to-end engine & MCP verify_claim + verify_predicate without key
    engine = ScholarEngine(predicate_store_path=":memory:")
    with patch.object(server, "get_engine", return_value=engine), \
         patch.object(engine.arxiv, "get_paper_by_id", new_callable=AsyncMock, return_value=paper), \
         patch.object(engine.openalex, "get_work_by_arxiv", new_callable=AsyncMock, return_value=None):
        claim_payload = json.loads(await server.scholar_verify_claim(claim.statement, paper.id))
        pred_payload = json.loads(
            await server.scholar_verify_predicate(
                paper.abstract,
                "Does this work evaluate on real hardware?",
            )
        )

    assert claim_payload["status"] == "unverified"
    assert claim_payload["result_state"] == "unverified"
    assert claim_payload["source"] == "unavailable"
    assert claim_payload["verification_probability"] is None
    assert claim_payload["auxiliary_heuristic"]["reliable"] is False
    assert "unverified" in claim_payload["warning"].lower()

    assert pred_payload["status"] == "unverified"
    assert pred_payload["verified"] is False
    assert pred_payload["probability"] is None
    assert pred_payload["source"] == "unavailable"
    assert pred_payload["auxiliary_heuristic"]["reliable"] is False
    assert pred_payload["auxiliary_heuristic"]["probability"] > 0.50
    assert "unverified" in pred_payload["warning"].lower()


@pytest.mark.asyncio
async def test_failclosed_whitespace_api_key_treated_as_missing(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "   ")
    client = JevClient()
    assert client.is_simulated is True
    _, evidence, claim = _high_overlap_paper_and_claim()
    checked = await PostRAGVerifier(client).verify_claim(claim, evidence)
    assert checked.status == "unverified"
    assert checked.failure_reason == "missing_api_key"
    assert checked.verification_probability is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_failclosed_invalid_api_key_returns_unverified(status_code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json={"error": "invalid api key"})

    paper, evidence, claim = _high_overlap_paper_and_claim()
    client = JevClient(api_key="invalid-key", transport=httpx.MockTransport(handler))
    checked = await PostRAGVerifier(client).verify_claim(claim, evidence)

    assert checked.status == "unverified"
    assert checked.status not in ("supported", "partial")
    assert checked.result_state == "unverified"
    assert checked.source == "unavailable"
    assert checked.verification_probability is None
    assert checked.contradiction_probability is None
    assert checked.failure_reason == f"http_{status_code}"
    assert checked.auxiliary_heuristic is not None
    assert checked.auxiliary_heuristic["reliable"] is False

    engine = ScholarEngine(predicate_store_path=":memory:", jev_client=client)
    with patch.object(server, "get_engine", return_value=engine), \
         patch.object(engine.arxiv, "get_paper_by_id", new_callable=AsyncMock, return_value=paper), \
         patch.object(engine.openalex, "get_work_by_arxiv", new_callable=AsyncMock, return_value=None):
        claim_payload = json.loads(await server.scholar_verify_claim(claim.statement, paper.id))
        pred_payload = json.loads(
            await server.scholar_verify_predicate(paper.abstract, "Does this work evaluate on real hardware?")
        )

    assert claim_payload["status"] == "unverified"
    assert claim_payload["verification_probability"] is None
    assert claim_payload["failure_reason"] == f"http_{status_code}"
    assert pred_payload["status"] == "unverified"
    assert pred_payload["verified"] is False
    assert pred_payload["probability"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("exc_cls", [httpx.ReadTimeout, httpx.ConnectTimeout])
async def test_failclosed_service_timeout_returns_unverified(exc_cls):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_cls("service timed out", request=request)

    paper, evidence, claim = _high_overlap_paper_and_claim()
    client = JevClient(api_key="test-key", transport=httpx.MockTransport(handler))
    checked = await PostRAGVerifier(client).verify_claim(claim, evidence)

    assert checked.status == "unverified"
    assert checked.status not in ("supported", "partial")
    assert checked.result_state == "unverified"
    assert checked.source == "unavailable"
    assert checked.verification_probability is None
    assert checked.contradiction_probability is None
    assert checked.failure_reason == "timeout"
    assert checked.auxiliary_heuristic is not None
    assert checked.auxiliary_heuristic["reliable"] is False

    engine = ScholarEngine(predicate_store_path=":memory:", jev_client=client)
    with patch.object(server, "get_engine", return_value=engine), \
         patch.object(engine.arxiv, "get_paper_by_id", new_callable=AsyncMock, return_value=paper), \
         patch.object(engine.openalex, "get_work_by_arxiv", new_callable=AsyncMock, return_value=None):
        claim_payload = json.loads(await server.scholar_verify_claim(claim.statement, paper.id))
        pred_payload = json.loads(
            await server.scholar_verify_predicate(paper.abstract, "Does this work evaluate on real hardware?")
        )

    assert claim_payload["status"] == "unverified"
    assert claim_payload["failure_reason"] == "timeout"
    assert claim_payload["verification_probability"] is None
    assert pred_payload["status"] == "unverified"
    assert pred_payload["verified"] is False
    assert pred_payload["failure_reason"] == "timeout"


@pytest.mark.asyncio
async def test_failclosed_partial_timeout_on_contradiction_call_still_returns_unverified():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        q = body["questions"]["q0"]["instructions"].lower()
        if "contradict" in q:
            raise httpx.ReadTimeout("contradiction check timed out", request=request)
        return httpx.Response(
            status_code=200,
            json={"model": "jev-latest", "answers": {"q0": {"noul": 0.96}}},
        )

    _, evidence, claim = _high_overlap_paper_and_claim()
    client = JevClient(api_key="test-key", transport=httpx.MockTransport(handler))
    checked = await PostRAGVerifier(client).verify_claim(claim, evidence)

    assert checked.status == "unverified"
    assert checked.result_state == "unverified"
    assert checked.source == "unavailable"
    assert checked.verification_probability is None
    assert checked.contradiction_probability is None
    assert checked.failure_reason == "timeout"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_body",
    [
        b"not json at all",
        b"null",
        b"[1, 2, 3]",
        b'{"model": "jev-latest", "answers": null}',
        b'{"model": "jev-latest", "answers": []}',
        b'{"model": "jev-latest", "answers": {"q0": {}}}',
        b'{"model": "jev-latest", "answers": {"q0": {"noul": true}}}',
        b'{"model": "jev-latest", "answers": {"q0": {"noul": 1.5}}}',
        b'{"model": "jev-latest", "answers": {"q0": {"noul": "NaN"}}}',
    ],
)
async def test_failclosed_malformed_response_returns_unverified(raw_body):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=raw_body)

    paper, evidence, claim = _high_overlap_paper_and_claim()
    client = JevClient(api_key="test-key", transport=httpx.MockTransport(handler))
    checked = await PostRAGVerifier(client).verify_claim(claim, evidence)

    assert checked.status == "unverified"
    assert checked.status not in ("supported", "partial")
    assert checked.result_state == "unverified"
    assert checked.source == "unavailable"
    assert checked.verification_probability is None
    assert checked.contradiction_probability is None
    assert checked.failure_reason == "malformed_response"
    assert checked.auxiliary_heuristic is not None
    assert checked.auxiliary_heuristic["reliable"] is False

    engine = ScholarEngine(predicate_store_path=":memory:", jev_client=client)
    with patch.object(server, "get_engine", return_value=engine), \
         patch.object(engine.arxiv, "get_paper_by_id", new_callable=AsyncMock, return_value=paper), \
         patch.object(engine.openalex, "get_work_by_arxiv", new_callable=AsyncMock, return_value=None):
        claim_payload = json.loads(await server.scholar_verify_claim(claim.statement, paper.id))
        pred_payload = json.loads(
            await server.scholar_verify_predicate(paper.abstract, "Does this work evaluate on real hardware?")
        )

    assert claim_payload["status"] == "unverified"
    assert claim_payload["failure_reason"] == "malformed_response"
    assert claim_payload["verification_probability"] is None
    assert pred_payload["status"] == "unverified"
    assert pred_payload["verified"] is False
    assert pred_payload["failure_reason"] == "malformed_response"


@pytest.mark.asyncio
async def test_failclosed_research_topic_under_timeout_returns_unverified_claims():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    paper, _, _ = _high_overlap_paper_and_claim()
    client = JevClient(api_key="test-key", transport=httpx.MockTransport(handler))
    engine = ScholarEngine(predicate_store_path=":memory:", jev_client=client)

    with patch.object(server, "get_engine", return_value=engine), \
         patch.object(engine.arxiv, "search", new_callable=AsyncMock, return_value=[paper]), \
         patch.object(engine.openalex, "get_work_by_arxiv", new_callable=AsyncMock, return_value=None):
        research_payload = json.loads(
            await server.scholar_research("loaded latency hardware", threshold=0.5, limit=1)
        )

    assert "warning" in research_payload
    assert research_payload["heuristic_evaluations"] > 0
    for p in research_payload["surviving_papers"]:
        for c in p["claims"]:
            assert c["status"] == "unverified"
            assert c["result_state"] == "unverified"
            assert c["source"] == "unavailable"
            assert c["prob"] is None
            assert c["failure_reason"] == "timeout"
            assert c["auxiliary_heuristic"]["reliable"] is False


@pytest.mark.asyncio
async def test_mcp_verify_claim_no_evidence_does_not_emit_heuristic_warning():
    empty_paper = Paper(id="2401.9002", title="Empty", abstract="   ", categories=["cs.NI"])
    engine = ScholarEngine(predicate_store_path=":memory:", jev_client=JevClient(force_simulation=True))
    with patch.object(server, "get_engine", return_value=engine), \
         patch.object(engine.arxiv, "get_paper_by_id", new_callable=AsyncMock, return_value=empty_paper), \
         patch.object(engine.openalex, "get_work_by_arxiv", new_callable=AsyncMock, return_value=None):
        payload = json.loads(await server.scholar_verify_claim("Any claim", empty_paper.id))

    assert payload["status"] == "no_evidence"
    assert payload["source"] == "none"
    assert "warning" not in payload

