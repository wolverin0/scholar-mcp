import httpx
import pytest
from unittest.mock import AsyncMock, patch
from scholar.retrieval.engine import ScholarEngine
from scholar.core.papers import Paper
from scholar.core.predicates import SemanticPredicate
from scholar.jev.client import JevClient
from scholar.sources.openalex import OpenAlexWork


@pytest.mark.asyncio
async def test_scholar_engine_research_loop_mocked():
    engine = ScholarEngine(
        predicate_store_path=":memory:",
        jev_client=JevClient(force_simulation=True),
    )

    mock_papers = [
        Paper(
            id="2401.1001",
            title="Field Measurements of Fixed PtMP Wireless Networks",
            abstract="We report real hardware experiments and loaded latency under asymmetric client traffic on QCA988x.",
            categories=["cs.NI"]
        ),
        Paper(
            id="2401.1002",
            title="Abstract Graph Flow Simulations",
            abstract="Pure simulation only with synthetic traffic models and analytical bounds.",
            categories=["cs.NI"]
        )
    ]

    mock_work = OpenAlexWork(
        openalex_id="https://openalex.org/W123",
        title="Field Measurements of Fixed PtMP Wireless Networks",
        cited_by_count=28
    )

    with patch.object(engine.arxiv, "search", new_callable=AsyncMock) as mock_search, \
         patch.object(engine.openalex, "get_work_by_arxiv", new_callable=AsyncMock) as mock_openalex:
        
        mock_search.return_value = mock_papers
        mock_openalex.return_value = mock_work

        predicates = [
            SemanticPredicate(
                id="P_real_hw",
                question="Does this paper evaluate real hardware?",
                default_threshold=0.50
            )
        ]

        report = await engine.research_topic("airmax loaded latency", predicates, max_candidates=2)

        assert report.total_candidates_found == 2
        assert report.surviving_papers_count == 1
        survivor = report.surviving_papers[0]
        assert survivor.id == "2401.1001"
        assert survivor.citations_count == 28
        assert survivor.openalex_id == "https://openalex.org/W123"
        assert len(report.verified_claims) >= 1
        assert report.execution_duration_sec >= 0
        assert report.warning is not None
        assert report.heuristic_evaluations > 0
        assert all(c.status not in ("supported", "partial") for c in report.verified_claims)


@pytest.mark.asyncio
async def test_mcp_scholar_research_emits_warning_and_never_supported_when_simulated():
    import json
    from scholar.mcp import server

    sim_engine = ScholarEngine(predicate_store_path=":memory:")
    sim_engine.jev = JevClient(force_simulation=True)
    sim_engine.gate.jev = sim_engine.jev
    sim_engine.verifier.jev = sim_engine.jev

    mock_papers = [
        Paper(
            id="2401.2001",
            title="Testbed Measurements of Wireless Scheduler",
            abstract="We deployed real hardware prototypes on an outdoor testbed with experimental measurements.",
            categories=["cs.NI"],
        )
    ]
    with patch.object(server, "engine", sim_engine), \
         patch.object(sim_engine.arxiv, "search", new_callable=AsyncMock, return_value=mock_papers), \
         patch.object(sim_engine.openalex, "get_work_by_arxiv", new_callable=AsyncMock, return_value=None):
        raw = await server.scholar_research(query="wireless testbed", limit=1)
        data = json.loads(raw)

    assert "warning" in data and data["warning"]
    for p in data["surviving_papers"]:
        assert p["semantic_sources"]
        for c in p["claims"]:
            assert c["status"] == "unverified_heuristic"
            assert c["status"] not in ("supported", "partial")


@pytest.mark.asyncio
async def test_research_topic_ranks_spans_by_query_and_only_attaches_evaluated_evidence():
    engine = ScholarEngine(
        predicate_store_path=":memory:",
        jev_client=JevClient(force_simulation=True),
    )
    shared_first = "Modern communication systems face diverse operational constraints in deployment."
    paper_a = Paper(
        id="2401.3001",
        title="Paper A",
        abstract=(
            f"{shared_first} "
            "Our field evaluation measures loaded latency and wifi airtime scheduling on real hardware."
        ),
        categories=["cs.NI"],
    )
    paper_b = Paper(
        id="2401.3002",
        title="Paper B",
        abstract=(
            f"{shared_first} "
            "We analyze thermal noise bounds in superconducting microwave cavities on hardware."
        ),
        categories=["cs.NI"],
    )

    evaluated_evidence_texts: list[tuple[str, str]] = []
    orig_verify = engine.verifier.verify_claim

    async def spy_verify(claim, cited_evidence):
        evaluated_evidence_texts.append((claim.paper_id, cited_evidence.text))
        return await orig_verify(claim, cited_evidence)

    predicates = [
        SemanticPredicate(id="P_hw", question="Does this paper evaluate real hardware?", default_threshold=0.5)
    ]
    with patch.object(engine.arxiv, "search", new_callable=AsyncMock, return_value=[paper_a, paper_b]), \
         patch.object(engine.openalex, "get_work_by_arxiv", new_callable=AsyncMock, return_value=None), \
         patch.object(engine.verifier, "verify_claim", side_effect=spy_verify):
        report = await engine.research_topic("loaded latency wifi", predicates, max_candidates=2)

    assert len(report.surviving_papers) == 2
    claims_by_paper = {p.id: p.claims for p in report.surviving_papers}
    # Paper A's top-ranked evidence must be its query-relevant second sentence, not the shared first sentence
    assert "loaded latency" in claims_by_paper["2401.3001"][0].supporting_evidence[0].text
    assert (
        claims_by_paper["2401.3001"][0].supporting_evidence[0].text
        != claims_by_paper["2401.3002"][0].supporting_evidence[0].text
    )
    # Every span in supporting_evidence across all claims must have been evaluated by verify_claim
    for claim in report.verified_claims:
        for ev in claim.supporting_evidence:
            assert (claim.paper_id, ev.text) in evaluated_evidence_texts


@pytest.mark.asyncio
async def test_empty_abstract_returns_no_evidence_without_calling_jev():
    engine = ScholarEngine(
        predicate_store_path=":memory:",
        jev_client=JevClient(force_simulation=True),
    )
    empty_paper = Paper(
        id="2401.4001",
        title="Paper Without Abstract",
        abstract="   ",
        categories=["cs.NI"],
    )

    with patch.object(engine.arxiv, "get_paper_by_id", new_callable=AsyncMock, return_value=empty_paper), \
         patch.object(engine.openalex, "get_work_by_arxiv", new_callable=AsyncMock, return_value=None), \
         patch.object(engine.jev, "evaluate_noul", new_callable=AsyncMock) as mock_jev:
        custom_claim = await engine.verify_custom_claim("Achieves 99% accuracy", "2401.4001")
        assert custom_claim is not None
        assert custom_claim.status == "no_evidence"
        assert custom_claim.supporting_evidence == []
        assert mock_jev.call_count == 0

    with patch.object(engine.arxiv, "search", new_callable=AsyncMock, return_value=[empty_paper]), \
         patch.object(engine.openalex, "get_work_by_arxiv", new_callable=AsyncMock, return_value=None), \
         patch.object(engine.verifier, "verify_claim", new_callable=AsyncMock) as mock_verify:
        report = await engine.research_topic("accuracy", predicates=[], max_candidates=1)
        assert len(report.verified_claims) == 1
        assert report.verified_claims[0].status == "no_evidence"
        assert report.verified_claims[0].supporting_evidence == []
        assert mock_verify.call_count == 0


@pytest.mark.asyncio
async def test_research_topic_falls_back_to_openalex_when_arxiv_raises():
    engine = ScholarEngine(
        predicate_store_path=":memory:",
        jev_client=JevClient(force_simulation=True),
    )
    oa_paper = Paper(
        id="openalex:W4242",
        title="OpenAlex Fallback Hardware Study",
        abstract="We evaluate prototype hardware on an outdoor testbed with field measurements.",
        openalex_id="https://openalex.org/W4242",
        citations_count=19,
        provenance_source="openalex",
    )
    predicates = [
        SemanticPredicate(id="P_hw", question="Does this paper evaluate real hardware?", default_threshold=0.5)
    ]

    with patch.object(engine.arxiv, "search", new_callable=AsyncMock, side_effect=httpx.TimeoutException("arXiv timeout")), \
         patch.object(engine.openalex, "search_works", new_callable=AsyncMock, return_value=[oa_paper]) as mock_oa:
        report = await engine.research_topic("hardware testbed", predicates, max_candidates=5)

    assert mock_oa.call_count == 1
    assert report.total_candidates_found == 1
    assert report.surviving_papers_count == 1
    assert report.surviving_papers[0].id == "openalex:W4242"
    assert report.surviving_papers[0].provenance_source == "openalex"


@pytest.mark.asyncio
async def test_inspect_paper_handles_openalex_id_without_raising():
    engine = ScholarEngine(
        predicate_store_path=":memory:",
        jev_client=JevClient(force_simulation=True),
    )
    oa_paper = Paper(
        id="openalex:W4242",
        title="OpenAlex Paper",
        abstract="Detailed abstract text.",
        openalex_id="https://openalex.org/W4242",
        citations_count=11,
        provenance_source="openalex",
    )

    with patch.object(engine.openalex, "get_work_by_id", new_callable=AsyncMock, return_value=oa_paper):
        paper = await engine.inspect_paper("openalex:W4242")

    assert paper is not None
    assert paper.id == "openalex:W4242"
    assert paper.provenance_source == "openalex"
