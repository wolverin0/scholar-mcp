"""
Scholar Engine Retrieval & Research Orchestrator.
Coordinates broad search, Jev semantic gating, citation expansion, and verification.
"""

from __future__ import annotations
import time
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

from scholar.core.papers import Paper, Claim, Evidence
from scholar.core.predicates import SemanticPredicate, PredicateStore
from scholar.sources.arxiv_api import ArxivAPIClient
from scholar.sources.openalex import OpenAlexClient, OpenAlexWork
from scholar.sources.duckdb_hf import DuckDBHuggingFaceClient
from scholar.jev.client import JevClient
from scholar.jev.gates import PreRAGGate, PostRAGVerifier, GateEvaluationReport


class ResearchReport(BaseModel):
    query: str
    total_candidates_found: int
    surviving_papers_count: int
    surviving_papers: List[Paper]
    rejection_reasons: Dict[str, List[str]]
    verified_claims: List[Claim] = Field(default_factory=list)
    execution_duration_sec: float


class ScholarEngine:
    """
    Unified scientific research engine for autonomous agents.
    """

    def __init__(
        self,
        predicate_store_path: str = ":memory:",
        typesafe_api_key: Optional[str] = None
    ):
        self.arxiv = ArxivAPIClient()
        self.openalex = OpenAlexClient()
        self.duckdb_hf = DuckDBHuggingFaceClient()
        self.jev = JevClient(api_key=typesafe_api_key)
        self.store = PredicateStore(predicate_store_path)
        self.gate = PreRAGGate(self.jev, self.store)
        self.verifier = PostRAGVerifier(self.jev)

    @staticmethod
    def extract_evidence_spans(paper: Paper, query: str = "") -> List[Evidence]:
        """
        Extracts salient evidence passages with exact character offsets from the full abstract.
        Prevents arbitrary truncation and maintains precise document provenance.
        """
        abstract = paper.abstract.strip()
        if not abstract:
            return []
            
        import re
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', abstract) if len(s.strip()) > 20]
        evidences: List[Evidence] = []
        for s in sentences:
            start_pos = abstract.find(s)
            end_pos = start_pos + len(s) if start_pos != -1 else len(s)
            evidences.append(Evidence(
                paper_id=paper.id,
                section="abstract",
                text=s,
                start_char=start_pos if start_pos != -1 else 0,
                end_char=end_pos,
                source_field="abstract",
                doc_id=paper.id,
                confidence=1.0
            ))
        return evidences

    async def search_papers(
        self,
        query: str,
        limit: int = 10,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None
    ) -> List[Paper]:
        """
        Executes a broad multi-source search with optional year bounds.
        """
        papers = await self.arxiv.search(query, max_results=limit * 2 if (year_min or year_max) else limit)
        if year_min or year_max:
            filtered = []
            for p in papers:
                if p.published_date:
                    try:
                        yr = int(p.published_date[:4])
                        if year_min and yr < year_min:
                            continue
                        if year_max and yr > year_max:
                            continue
                    except ValueError:
                        pass
                filtered.append(p)
                if len(filtered) >= limit:
                    break
            return filtered
        return papers[:limit]

    async def inspect_paper(self, paper_id: str) -> Optional[Paper]:
        """
        Fetches paper, merges OpenAlex citation metrics, and computes existing predicates.
        """
        paper = await self.arxiv.get_paper_by_id(paper_id)
        if not paper:
            # Fallback to DuckDB Parquet
            paper = self.duckdb_hf.query_paper_metadata_by_id(paper_id)
            if not paper:
                return None

        # Fetch OpenAlex citation graph
        work = await self.openalex.get_work_by_arxiv(paper_id)
        if work:
            paper.openalex_id = work.openalex_id
            paper.citations_count = work.cited_by_count
            if work.doi:
                paper.doi = work.doi

        # Attach stored predicates
        stored_preds = self.store.get_paper_predicates(paper.id)
        paper.semantic_features.update(stored_preds)

        return paper

    async def verify_custom_claim(self, claim_statement: str, paper_id: str) -> Optional[Claim]:
        """
        Verifies a user or agent-provided claim against a specific paper's full abstract/text.
        Identifies the best matching evidence span with exact character offsets.
        """
        import re
        paper = await self.inspect_paper(paper_id)
        if not paper:
            return None
            
        spans = self.extract_evidence_spans(paper)
        if not spans:
            evidence = Evidence(
                paper_id=paper.id,
                section="abstract",
                text=paper.abstract,
                start_char=0,
                end_char=len(paper.abstract),
                source_field="abstract",
                doc_id=paper.id
            )
        else:
            claim_words = set(re.findall(r'\w+', claim_statement.lower()))
            best_span = max(spans, key=lambda s: len(claim_words.intersection(set(re.findall(r'\w+', s.text.lower())))))
            evidence = best_span

        claim = Claim(
            id=f"claim_{paper.id}_{int(time.time())}",
            statement=claim_statement,
            paper_id=paper.id,
            document_id=paper.id
        )
        return await self.verifier.verify_claim(claim, evidence)

    async def research_topic(
        self,
        query: str,
        predicates: List[SemanticPredicate],
        max_candidates: int = 15
    ) -> ResearchReport:
        """
        Executes the full end-to-end autonomous research loop:
        1. Query Discovery
        2. Jev Pre-RAG Gatekeeper
        3. Citation Graph Enrichment
        4. Claim Extraction & Span-Level Verification
        """
        t0 = time.perf_counter()

        # Step 1: Broad discovery
        candidates = await self.arxiv.search(query, max_results=max_candidates)

        # Step 2: Pre-RAG Semantic Screening
        gate_report = await self.gate.screen_papers(candidates, predicates)
        survivors = gate_report.surviving_papers

        # Step 3: Citation Graph Expansion & Enrichment for survivors
        for paper in survivors:
            work = await self.openalex.get_work_by_arxiv(paper.id)
            if work:
                paper.openalex_id = work.openalex_id
                paper.citations_count = work.cited_by_count

        # Step 4: Verification of candidate findings / claims with exact spans
        verified_claims: List[Claim] = []
        for paper in survivors:
            spans = self.extract_evidence_spans(paper, query)
            primary_evidence = spans[0] if spans else Evidence(
                paper_id=paper.id,
                section="abstract",
                text=paper.abstract,
                start_char=0,
                end_char=len(paper.abstract),
                source_field="abstract",
                doc_id=paper.id
            )
            
            claim_stmt = f"Paper '{paper.title}' establishes verifiable methodologies or empirical outcomes for {query}."
            claim = Claim(
                id=f"claim_{paper.id}",
                statement=claim_stmt,
                paper_id=paper.id,
                document_id=paper.id
            )
            checked_claim = await self.verifier.verify_claim(claim, primary_evidence)
            if len(spans) > 1:
                checked_claim.supporting_evidence.extend(spans[1:3])
                
            paper.claims.append(checked_claim)
            verified_claims.append(checked_claim)

        duration = round(time.perf_counter() - t0, 3)

        return ResearchReport(
            query=query,
            total_candidates_found=len(candidates),
            surviving_papers_count=len(survivors),
            surviving_papers=survivors,
            rejection_reasons=gate_report.rejection_reasons,
            verified_claims=verified_claims,
            execution_duration_sec=duration
        )
