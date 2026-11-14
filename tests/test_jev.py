import json
import logging
import httpx
import pytest
from scholar.core.papers import Paper, Claim, Evidence
from scholar.core.predicates import SemanticPredicate, PredicateStore
from scholar.jev.client import JevClient
from scholar.jev.gates import PreRAGGate, PostRAGVerifier


@pytest.mark.asyncio
async def test_jev_client_simulation():
    client = JevClient(force_simulation=True)
    assert client.is_simulated is True

    text = "We evaluate our scheduler on an outdoor 802.11ac testbed with real hardware and CPE devices."
    decision = await client.evaluate_noul(text, "Does this paper evaluate real hardware?")
    
    assert decision.probability > 0.50
    assert decision.latency_ms >= 0


@pytest.mark.asyncio
async def test_pre_rag_gate_filtering():
    client = JevClient()
    store = PredicateStore(":memory:")
    gate = PreRAGGate(client, store)

    paper_hw = Paper(
        id="2401.0001",
        title="Field Trial of PtMP MAC Scheduler on Atheros Hardware",
        abstract="We deployed prototype hardware and evaluated loaded latency across 40 customer CPEs."
    )
    paper_sim = Paper(
        id="2401.0002",
        title="Theoretical Bounds on Queueing in Abstract Networks",
        abstract="This is a purely theoretical paper with NS-3 simulation only. No hardware experiments."
    )

    predicates = [
        SemanticPredicate(
            id="P_hardware",
            question="Does this paper evaluate real hardware?",
            default_threshold=0.50
        )
    ]

    report = await gate.screen_papers([paper_hw, paper_sim], predicates)

    assert report.total_candidates == 2
    assert report.passed_count == 1
    assert report.rejected_count == 1
    assert report.surviving_papers[0].id == "2401.0001"
    assert "2401.0002" in report.rejection_reasons


@pytest.mark.asyncio
async def test_post_rag_verifier():
    client = JevClient()
    verifier = PostRAGVerifier(client)

    evidence = Evidence(
        paper_id="2401.0001",
        section="results",
        text="The proposed airtime scheduler reduces 99th percentile loaded latency by 68% on QCA988x hardware."
    )

    claim = Claim(
        id="c1",
        statement="The scheduler demonstrates loaded latency reductions on physical hardware.",
        paper_id="2401.0001"
    )

    verified = await verifier.verify_claim(claim, evidence)
    assert verified.status in ["supported", "partial"]
    assert verified.verification_probability is not None
    assert verified.verification_probability > 0.40


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code,payload",
    [
        (401, {"error": "unauthorized"}),
        (500, {"error": "server error"}),
        (200, {"model": "jev-latest", "answers": {"q0": {}}}),
        (200, {"model": "jev-latest", "answers": {"q0": {"noul": 1.7}}}),
        (200, {"model": "jev-latest", "answers": {"q0": {"noul": "NaN"}}}),
    ],
)
async def test_jev_client_http_and_payload_fallbacks_log_warning(caplog, status_code, payload):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json=payload)

    transport = httpx.MockTransport(handler)
    client = JevClient(api_key="test-key", transport=transport)

    with caplog.at_level(logging.WARNING, logger="scholar.jev.client"):
        decision = await client.evaluate_noul(
            "We deployed prototype hardware on an outdoor testbed.",
            "Does this paper evaluate real hardware?",
        )

    assert decision.source == "heuristic"
    assert decision.is_heuristic is True
    assert decision.model_version == "jev-simulated-fallback"
    assert any("falling back to heuristic" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_jev_client_valid_live_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={"model": "jev-latest", "answers": {"q0": {"noul": 0.87}}},
        )

    client = JevClient(api_key="test-key", transport=httpx.MockTransport(handler))
    decision = await client.evaluate_noul("Some evidence", "Some question?")

    assert decision.source == "live"
    assert decision.is_heuristic is False
    assert decision.probability == 0.87
    assert decision.model_version == "jev-latest"


@pytest.mark.asyncio
async def test_jev_batch_missing_answer_falls_back_with_warning(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={"model": "jev-latest", "answers": {"q_0": {"noul": 0.9}}},
        )

    client = JevClient(api_key="test-key", transport=httpx.MockTransport(handler))
    questions = ["First question?", "Second question?"]

    with caplog.at_level(logging.WARNING, logger="scholar.jev.client"):
        res = await client.batch_evaluate_predicates("Testbed hardware evidence.", questions)

    assert len(res) == 2
    assert all(dec.source == "heuristic" and dec.is_heuristic for dec in res.values())
    assert any("falling back to heuristic" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_jev_batch_valid_live_response():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert set(body["questions"].keys()) == {"q_0", "q_1"}
        return httpx.Response(
            status_code=200,
            json={
                "model": "jev-latest",
                "answers": {"q_0": {"noul": 0.91}, "q_1": {"noul": 0.22}},
            },
        )

    client = JevClient(api_key="test-key", transport=httpx.MockTransport(handler))
    res = await client.batch_evaluate_predicates("Evidence", ["Q1?", "Q2?"])

    assert res["Q1?"].source == "live"
    assert res["Q1?"].is_heuristic is False
    assert res["Q1?"].probability == 0.91
    assert res["Q2?"].source == "live"
    assert res["Q2?"].is_heuristic is False
    assert res["Q2?"].probability == 0.22
