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
