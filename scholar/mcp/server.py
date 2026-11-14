"""
FastMCP Server for Scholar Engine.
Exposes high-level research capabilities to Claude Code, Codex, Antigravity, and other agents.
"""

from __future__ import annotations
import json
import logging
import os
from mcp.server.fastmcp import FastMCP
from scholar.retrieval.engine import ScholarEngine
from scholar.core.predicates import SemanticPredicate

logger = logging.getLogger(__name__)

# Initialize FastMCP application
mcp = FastMCP("ScholarEngine", dependencies=["httpx", "pydantic", "duckdb"])
engine = ScholarEngine()

if engine.jev.is_simulated:
    logger.warning(
        "ScholarEngine started without TYPESAFE_API_KEY; running in unverified heuristic mode."
    )


@mcp.tool()
async def scholar_search(
    query: str,
    limit: int = 5,
    year_min: int | None = None,
    year_max: int | None = None
) -> str:
    """
    Searches scientific papers on arXiv by topic, keywords, or title.
    Supports optional year bounds (year_min, year_max).
    Returns structured list of paper IDs, titles, categories, and abstracts.
    """
    papers = await engine.search_papers(query, limit=limit, year_min=year_min, year_max=year_max)
    res = []
    for p in papers:
        res.append({
            "id": p.id,
            "title": p.title,
            "categories": p.categories,
            "published": p.published_date,
            "abstract": p.abstract[:300] + "..." if len(p.abstract) > 300 else p.abstract,
            "pdf_url": p.pdf_url
        })
    return json.dumps(res, indent=2)


@mcp.tool()
async def scholar_inspect(paper_id: str) -> str:
    """
    Inspects a specific scientific paper by arXiv ID.
    Merges OpenAlex citation metrics, authors, and stored semantic predicates.
    """
    paper = await engine.inspect_paper(paper_id)
    if not paper:
        return json.dumps({"error": f"Paper {paper_id} not found."})

    res = {
        "id": paper.id,
        "title": paper.title,
        "abstract": paper.abstract,
        "categories": paper.categories,
        "citations_count": paper.citations_count,
        "openalex_id": paper.openalex_id,
        "doi": paper.doi,
        "semantic_features": paper.semantic_features,
        "semantic_sources": paper.semantic_sources,
    }
    if any(src != "live" for src in paper.semantic_sources.values()):
        res["warning"] = "Some semantic features were evaluated using unverified heuristics."
    return json.dumps(res, indent=2)


@mcp.tool()
async def scholar_verify_claim(claim: str, paper_id: str) -> str:
    """
    Verifies an empirical or scientific claim against a specific paper's full abstract/text.
    Extracts the most salient evidence passage with exact character offsets.
    Outputs strict status (supported, contradicted, unsupported), verification probability,
    provenance (live vs. heuristic), and exact evidence spans.
    """
    checked = await engine.verify_custom_claim(claim, paper_id)
    if not checked:
        return json.dumps({"error": f"Paper {paper_id} could not be retrieved for claim verification."})

    evidences = [
        {
            "paper_id": ev.paper_id,
            "text": ev.text,
            "start_char": ev.start_char,
            "end_char": ev.end_char,
            "source_field": ev.source_field,
            "confidence": ev.confidence
        }
        for ev in checked.supporting_evidence
    ]

    res = {
        "claim": checked.statement,
        "paper_id": checked.paper_id,
        "status": checked.status,
        "result_state": checked.result_state,
        "verification_probability": checked.verification_probability,
        "contradiction_probability": checked.contradiction_probability,
        "contradiction_source": checked.contradiction_source,
        "source": checked.source,
        "model_version": checked.model_version,
        "evidence_spans": evidences
    }
    if checked.source != "live":
        res["warning"] = (
            "Verification used unverified local heuristics "
            "(TYPESAFE_API_KEY not set or Jev API unavailable)."
        )
    return json.dumps(res, indent=2)


@mcp.tool()
async def scholar_verify_predicate(state_text: str, question: str) -> str:
    """
    Directly evaluates a boolean or probabilistic proposition against any state or text passage.
    Returns probability in [0.0, 1.0], decision latency, and provenance source (live vs heuristic).
    """
    decision = await engine.jev.evaluate_noul(state_text, question)
    res = {
        "question": decision.question,
        "probability": decision.probability,
        "latency_ms": decision.latency_ms,
        "source": decision.source,
        "is_heuristic": decision.is_heuristic,
        "model_version": decision.model_version
    }
    if decision.source != "live":
        res["warning"] = (
            "Evaluation used unverified local heuristics "
            "(TYPESAFE_API_KEY not set or Jev API unavailable)."
        )
    return json.dumps(res, indent=2)


@mcp.tool()
async def scholar_research(
    query: str,
    domain: str = "general",
    threshold: float = 0.50,
    limit: int = 10
) -> str:
    """
    Executes an autonomous scientific research loop:
    1. Discovers candidates on arXiv.
    2. Runs Jev System One semantic gatekeeper to filter non-empirical/incompatible papers.
    3. Fetches citation graphs and verifies claims against evidence text with exact spans.
    Returns surviving evidence-backed papers with confidence metrics.
    """
    predicates = [
        SemanticPredicate(
            id="P_empirical",
            question="Does this work present empirical evaluations or experimental measurements?",
            default_threshold=threshold
        ),
        SemanticPredicate(
            id="P_applicable",
            question=f"Are the methods or results in this paper applicable to: {query}?",
            default_threshold=threshold
        )
    ]

    report = await engine.research_topic(query, predicates, max_candidates=limit)
    
    surviving = []
    for p in report.surviving_papers:
        claims = [
            {
                "statement": c.statement,
                "status": c.status,
                "prob": c.verification_probability,
                "source": c.source,
                "result_state": c.result_state,
                "evidence_spans": [
                    {
                        "start_char": ev.start_char,
                        "end_char": ev.end_char,
                        "source_field": ev.source_field,
                        "text": ev.text
                    }
                    for ev in c.supporting_evidence
                ]
            }
            for c in p.claims
        ]
        surviving.append({
            "id": p.id,
            "title": p.title,
            "citations": p.citations_count,
            "semantic_features": p.semantic_features,
            "semantic_sources": p.semantic_sources,
            "claims": claims
        })

    output = {
        "query": query,
        "duration_sec": report.execution_duration_sec,
        "candidates_found": report.total_candidates_found,
        "passed_gatekeeper": report.surviving_papers_count,
        "heuristic_evaluations": report.heuristic_evaluations,
        "surviving_papers": surviving,
        "screened_out_count": len(report.rejection_reasons),
        "rejection_sample": {k: v for k, v in list(report.rejection_reasons.items())[:3]}
    }
    if report.warning:
        output["warning"] = report.warning
    return json.dumps(output, indent=2)


def main():
    if not os.environ.get("TYPESAFE_API_KEY"):
        logger.warning(
            "TYPESAFE_API_KEY is not set; ScholarEngine MCP tools will emit heuristic evaluations marked unverified_heuristic."
        )
    mcp.run()


if __name__ == "__main__":
    main()
