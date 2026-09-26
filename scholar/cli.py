"""
Scholar Engine CLI.
Provides terminal interface for human operators and script automation.
"""

from __future__ import annotations
import asyncio
import sys
import argparse
from scholar.retrieval.engine import ScholarEngine
from scholar.core.predicates import SemanticPredicate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scholar",
        description="Scholar Engine: High-speed Scientific Literature Semantic Compiler"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Command: search
    p_search = subparsers.add_parser("search", help="Search papers on arXiv")
    p_search.add_argument("query", help="Search query string")
    p_search.add_argument("--limit", type=int, default=5, help="Max results")

    # Command: inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect a specific paper")
    p_inspect.add_argument("paper_id", help="arXiv ID (e.g. 2401.12345)")

    # Command: research
    p_research = subparsers.add_parser("research", help="Run full research loop with Jev semantic gating")
    p_research.add_argument("query", help="Research question or topic")
    p_research.add_argument("--domain", default="wireless", help="Topic domain (e.g. wireless, ai, memory)")
    p_research.add_argument("--threshold", type=float, default=0.50, help="Min probability threshold for gating")
    p_research.add_argument("--limit", type=int, default=10, help="Initial candidates to screen")

    return parser


async def run_cli():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    engine = ScholarEngine()

    if args.command == "search":
        print(f"[*] Searching arXiv for: '{args.query}' (limit={args.limit})...")
        papers = await engine.search_papers(args.query, limit=args.limit)
        print(f"[+] Found {len(papers)} papers:\n")
        for i, p in enumerate(papers, 1):
            print(f"{i}. [{p.id}] {p.title}")
            print(f"   Categories: {', '.join(p.categories[:3])} | Published: {p.published_date}")
            print(f"   Abstract: {p.abstract[:140]}...\n")

    elif args.command == "inspect":
        print(f"[*] Inspecting paper: {args.paper_id}...")
        paper = await engine.inspect_paper(args.paper_id)
        if not paper:
            print(f"[-] Paper {args.paper_id} not found.")
            sys.exit(1)

        print(f"\n[+] Title: {paper.title}")
        print(f"    ID: {paper.id} | DOI: {paper.doi or 'N/A'}")
        print(f"    Citations (OpenAlex): {paper.citations_count}")
        print(f"    OpenAlex ID: {paper.openalex_id or 'N/A'}")
        print(f"    Categories: {', '.join(paper.categories)}")
        print("\n--- Abstract ---")
        print(paper.abstract)

        if paper.semantic_features:
            print("\n--- Semantic Predicates ---")
            for k, v in paper.semantic_features.items():
                print(f"    {k}: {v:.2f}")

    elif args.command == "research":
        print(f"[*] Initiating autonomous research on: '{args.query}' (threshold={args.threshold})...")
        # Define domain-specific predicates
        predicates = [
            SemanticPredicate(
                id="P_empirical",
                question="Does this work present empirical evaluations or experimental measurements?",
                default_threshold=args.threshold
            ),
            SemanticPredicate(
                id="P_applicable",
                question=f"Are the methods or results in this paper applicable to: {args.query}?",
                default_threshold=args.threshold
            )
        ]

        report = await engine.research_topic(args.query, predicates, max_candidates=args.limit)
        print(f"\n[+] Research Completed in {report.execution_duration_sec}s")
        print(f"    Candidates Found: {report.total_candidates_found}")
        print(f"    Passed Gatekeeper: {report.surviving_papers_count}")
        print(f"    Rejected: {len(report.rejection_reasons)}")

        if report.rejection_reasons:
            print("\n--- Gatekeeper Screened Out ---")
            for p_id, reasons in list(report.rejection_reasons.items())[:5]:
                print(f"  * Paper [{p_id}]: {'; '.join(reasons)}")

        if report.surviving_papers:
            print("\n=== Surviving Evidence-Backed Papers ===")
            for p in report.surviving_papers:
                print(f"\n* [{p.id}] {p.title} (Citations: {p.citations_count})")
                print(f"  P(Empirical): {p.semantic_features.get('P_empirical', 0):.2f} | P(Applicable): {p.semantic_features.get('P_applicable', 0):.2f}")
                for c in p.claims:
                    print(f"  Claim Status: [{c.status.upper()}] (P={c.verification_probability or 0:.2f})")


def main():
    asyncio.run(run_cli())


if __name__ == "__main__":
    main()
