import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from scholar.core.papers import Claim, Evidence, Paper
from scholar.jev.client import JevClient, JevDecision
from scholar.retrieval.engine import ResearchReport, ScholarEngine
from scholar.mcp import server
from scholar import cli


def _make_fake_engine() -> MagicMock:
    fake = MagicMock(spec=ScholarEngine)
    fake.jev = JevClient(force_simulation=True)

    sample_paper = Paper(
        id="2401.12345",
        title="Deterministic Wireless Scheduling",
        abstract="We evaluate real hardware on an outdoor testbed with sub-5ms latency.",
        categories=["cs.NI"],
        published_date="2024-01-15T00:00:00Z",
        pdf_url="https://arxiv.org/pdf/2401.12345",
        citations_count=12,
        openalex_id="https://openalex.org/W100",
        doi="10.1000/test",
        semantic_features={"P_empirical": 0.85},
        semantic_sources={"P_empirical": "heuristic"},
    )
    sample_claim = Claim(
        id="claim_1",
        statement="Sub-5ms latency on hardware",
        paper_id="2401.12345",
        status="unverified_heuristic",
        result_state="heuristic",
        verification_probability=0.80,
        contradiction_probability=0.05,
        contradiction_source="heuristic",
        source="heuristic",
        model_version="jev-simulated-v1",
        supporting_evidence=[
            Evidence(
                paper_id="2401.12345",
                text="We evaluate real hardware on an outdoor testbed with sub-5ms latency.",
                start_char=0,
                end_char=69,
                source_field="abstract",
                doc_id="2401.12345",
            )
        ],
    )
    sample_paper.claims = [sample_claim]

    fake.search_papers = AsyncMock(return_value=[sample_paper])
    fake.inspect_paper = AsyncMock(return_value=sample_paper)
    fake.verify_custom_claim = AsyncMock(return_value=sample_claim)
    fake.jev = MagicMock()
    fake.jev.is_simulated = True
    fake.jev.evaluate_noul = AsyncMock(
        return_value=JevDecision(
            question="Is this empirical?",
            probability=0.85,
            latency_ms=0.2,
            model_version="jev-simulated-v1",
            source="heuristic",
            is_heuristic=True,
        )
    )
    fake.research_topic = AsyncMock(
        return_value=ResearchReport(
            query="wireless latency",
            total_candidates_found=2,
            surviving_papers_count=1,
            surviving_papers=[sample_paper],
            rejection_reasons={"2401.99999": ["Failed P_empirical"]},
            verified_claims=[sample_claim],
            heuristic_evaluations=2,
            warning="Results include unverified heuristic evaluations.",
            execution_duration_sec=0.01,
        )
    )
    return fake


def test_server_uses_lazy_get_engine():
    assert hasattr(server, "get_engine")
    assert server._engine is None


@pytest.mark.asyncio
async def test_mcp_five_tools_with_fake_engine():
    fake = _make_fake_engine()
    with patch.object(server, "get_engine", return_value=fake):
        search_res = json.loads(await server.scholar_search("wireless", limit=5))
        assert len(search_res) == 1
        assert search_res[0]["id"] == "2401.12345"

        inspect_res = json.loads(await server.scholar_inspect("2401.12345"))
        assert inspect_res["id"] == "2401.12345"
        assert inspect_res["semantic_sources"] == {"P_empirical": "heuristic"}
        assert "warning" in inspect_res

        claim_res = json.loads(await server.scholar_verify_claim("Sub-5ms latency", "2401.12345"))
        assert claim_res["status"] == "unverified_heuristic"
        assert claim_res["contradiction_probability"] == 0.05
        assert "warning" in claim_res

        pred_res = json.loads(await server.scholar_verify_predicate("Real hardware testbed", "Empirical?"))
        assert pred_res["source"] == "heuristic"
        assert "warning" in pred_res

        research_res = json.loads(await server.scholar_research("wireless latency", threshold=0.5, limit=5))
        assert research_res["passed_gatekeeper"] == 1
        assert "warning" in research_res


def test_cli_build_parser_and_commands(capsys):
    parser = cli.build_parser()
    args_search = parser.parse_args(["search", "wifi latency", "--limit", "3"])
    assert args_search.command == "search"
    assert args_search.limit == 3

    args_inspect = parser.parse_args(["inspect", "2401.12345"])
    assert args_inspect.command == "inspect"
    assert args_inspect.paper_id == "2401.12345"

    args_research = parser.parse_args(["research", "airtime", "--threshold", "0.6", "--limit", "4"])
    assert args_research.command == "research"
    assert args_research.threshold == 0.6


@pytest.mark.asyncio
async def test_cli_run_in_process_with_fake_engine(capsys):
    fake = _make_fake_engine()
    await cli.run_cli(["search", "wireless", "--limit", "2"], engine=fake)
    out_search = capsys.readouterr().out
    assert "2401.12345" in out_search

    await cli.run_cli(["inspect", "2401.12345"], engine=fake)
    out_inspect = capsys.readouterr().out
    assert "Deterministic Wireless Scheduling" in out_inspect

    await cli.run_cli(["research", "wireless latency", "--limit", "2"], engine=fake)
    out_research = capsys.readouterr().out
    assert "UNVERIFIED_HEURISTIC" in out_research
    assert "WARNING" in out_research


def test_scholar_engine_injected_jev_client_ignores_env_api_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "should-not-be-used")
    engine = ScholarEngine(jev_client=JevClient(force_simulation=True))
    assert engine.jev.is_simulated is True


@pytest.mark.asyncio
async def test_mcp_tools_validate_limit_and_threshold_bounds():
    fake = _make_fake_engine()
    with patch.object(server, "get_engine", return_value=fake):
        with pytest.raises(ValueError, match="limit"):
            await server.scholar_search("test", limit=10**6)
        with pytest.raises(ValueError, match="limit"):
            await server.scholar_search("test", limit=0)
        with pytest.raises(ValueError, match="limit"):
            await server.scholar_research("test", limit=10**6)
        with pytest.raises(ValueError, match="threshold"):
            await server.scholar_research("test", threshold=1.5)
        with pytest.raises(ValueError, match="threshold"):
            await server.scholar_research("test", threshold=-0.1)


@pytest.mark.asyncio
async def test_mcp_scholar_research_propagates_domain_and_removes_dead_citation_graph():
    from scholar.sources.openalex import OpenAlexClient

    assert not hasattr(OpenAlexClient, "get_citation_graph")

    fake = _make_fake_engine()
    with patch.object(server, "get_engine", return_value=fake):
        res = json.loads(
            await server.scholar_research("wireless latency", domain="wireless", threshold=0.5, limit=5)
        )
    assert res["domain"] == "wireless"
    preds = fake.research_topic.call_args.args[1]
    assert all(p.domain == "wireless" for p in preds)
