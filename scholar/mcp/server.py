"""
FastMCP Server for Scholar Engine.
Exposes high-level research capabilities to Claude Code, Codex, Antigravity, and other agents.
"""

from __future__ import annotations
import json
from mcp.server.fastmcp import FastMCP
from scholar.retrieval.engine import ScholarEngine
from scholar.core.predicates import SemanticPredicate

# Initialize FastMCP application
mcp = FastMCP("ScholarEngine", dependencies=["httpx", "pydantic", "duckdb"])
engine = ScholarEngine()


@mcp.tool()
async def scholar_search(query: str, limit: int = 5) -> str:
    """
    Searches scientific papers on arXiv by topic, keywords, or title.
    Returns structured list of paper IDs, titles, categories, and abstracts.
    """
    papers = await engine.search_papers(query, limit=limit)
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
        "semantic_features": paper.semantic_features
    }
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
    3. Fetches citation graphs and verifies claims against evidence text.
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
            {"statement": c.statement, "status": c.status, "prob": c.verification_probability}
            for c in p.claims
        ]
        surviving.append({
            "id": p.id,
            "title": p.title,
            "citations": p.citations_count,
            "semantic_features": p.semantic_features,
            "claims": claims
        })

    output = {
        "query": query,
        "duration_sec": report.execution_duration_sec,
        "candidates_found": report.total_candidates_found,
        "passed_gatekeeper": report.surviving_papers_count,
        "surviving_papers": surviving,
        "screened_out_count": len(report.rejection_reasons),
        "rejection_sample": {k: v for k, v in list(report.rejection_reasons.items())[:3]}
    }
    return json.dumps(output, indent=2)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
