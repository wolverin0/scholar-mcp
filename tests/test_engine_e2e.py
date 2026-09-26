import pytest
from unittest.mock import AsyncMock, patch
from scholar.retrieval.engine import ScholarEngine
from scholar.core.papers import Paper
from scholar.core.predicates import SemanticPredicate
from scholar.sources.openalex import OpenAlexWork


@pytest.mark.asyncio
async def test_scholar_engine_research_loop_mocked():
    engine = ScholarEngine(predicate_store_path=":memory:")

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
            abstract="Pure simulation only with synthetic traffic models. No testbed measurements.",
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
