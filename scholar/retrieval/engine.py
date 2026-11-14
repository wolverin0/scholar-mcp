"""
Scholar Engine Retrieval & Research Orchestrator.
Coordinates broad search, Jev semantic gating, citation expansion, and verification.
"""

from __future__ import annotations
import asyncio
import logging
import re
import time
import duckdb
import httpx
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

from scholar.core.papers import Paper, Claim, Evidence
from scholar.core.predicates import SemanticPredicate, PredicateStore
from scholar.sources.arxiv_api import ArxivAPIClient
from scholar.sources.openalex import OpenAlexClient, OpenAlexWork
from scholar.sources.duckdb_hf import DuckDBHuggingFaceClient
from scholar.jev.client import JevClient
from scholar.jev.gates import PreRAGGate, PostRAGVerifier, GateEvaluationReport

logger = logging.getLogger(__name__)


_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "our", "paper", "study", "that",
    "the", "their", "this", "to", "was", "we", "were", "with",
})


class ResearchReport(BaseModel):
    query: str
    total_candidates_found: int
    surviving_papers_count: int
    surviving_papers: List[Paper]
    rejection_reasons: Dict[str, List[str]]
    verified_claims: List[Claim] = Field(default_factory=list)
    heuristic_evaluations: int = 0
    warning: Optional[str] = None
    execution_duration_sec: float


class ScholarEngine:
    """
    Unified scientific research engine for autonomous agents.
    """

    def __init__(
        self,
        predicate_store_path: str = ":memory:",
        typesafe_api_key: Optional[str] = None,
        jev_client: Optional[JevClient] = None,
    ):
        self.arxiv = ArxivAPIClient()
        self.openalex = OpenAlexClient()
        self.duckdb_hf = DuckDBHuggingFaceClient()
        self.jev = jev_client or JevClient(api_key=typesafe_api_key)
        self.store = PredicateStore(predicate_store_path)
        self.gate = PreRAGGate(self.jev, self.store)
        self.verifier = PostRAGVerifier(self.jev)

    @staticmethod
    def extract_evidence_spans(paper: Paper, query: str = "") -> List[Evidence]:
        """
        Extracts salient evidence passages with exact character offsets from the full abstract.
        Prevents arbitrary truncation and maintains precise document provenance.
        """
        raw_abstract = paper.abstract
        if not raw_abstract.strip():
            return []

        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', raw_abstract.strip()) if len(s.strip()) > 20]
        if not sentences:
            sentences = [raw_abstract.strip()]

        evidences: List[Evidence] = []
        cursor = 0
        for s in sentences:
            start_pos = raw_abstract.find(s, cursor)
            if start_pos == -1:
                start_pos = raw_abstract.find(s)
            if start_pos != -1:
                end_pos = start_pos + len(s)
                cursor = end_pos
            else:
                start_pos = 0
                end_pos = len(s)
            evidences.append(Evidence(
                paper_id=paper.id,
                section="abstract",
                text=s,
                start_char=start_pos,
                end_char=end_pos,
                source_field="abstract",
                doc_id=paper.id,
                confidence=1.0
            ))
        return evidences

    @staticmethod
    def _content_tokens(text: str) -> set[str]:
        tokens = set(re.findall(r"\w+", text.lower()))
        filtered = {t for t in tokens if t not in _STOPWORDS and len(t) > 1}
        return filtered or tokens

    @classmethod
    def rank_evidence_spans(
        cls,
        spans: List[Evidence],
        query_text: str,
        top_k: Optional[int] = None,
    ) -> List[Evidence]:
        """Ranks evidence spans by stopword-filtered token overlap with query_text."""
        if not spans:
            return []
        target_tokens = cls._content_tokens(query_text)
        ranked = sorted(
            spans,
            key=lambda s: len(target_tokens.intersection(cls._content_tokens(s.text))),
            reverse=True,
        )
        return ranked[:top_k] if top_k is not None else ranked

    async def _search_with_fallback(self, query: str, max_results: int) -> List[Paper]:
        """Searches arXiv first, falling back to OpenAlex on HTTP error or empty result."""
        try:
            papers = await self.arxiv.search(query, max_results=max_results)
        except httpx.HTTPError as exc:
            logger.warning("arXiv search failed (%s: %s); falling back to OpenAlex", type(exc).__name__, exc)
            papers = []

        if papers:
            return papers

        try:
            return await self.openalex.search_works(query, limit=max_results)
        except httpx.HTTPError as exc:
            logger.warning("OpenAlex fallback search failed (%s: %s)", type(exc).__name__, exc)
            return []

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
        has_year_bounds = year_min is not None or year_max is not None
        papers = await self._search_with_fallback(query, max_results=limit * 2 if has_year_bounds else limit)
        if has_year_bounds:
            filtered = []
            for p in papers:
                if not p.published_date:
                    continue
                try:
                    yr = int(p.published_date[:4])
                except ValueError:
                    continue
                if year_min is not None and yr < year_min:
                    continue
                if year_max is not None and yr > year_max:
                    continue
                filtered.append(p)
                if len(filtered) >= limit:
                    break
            return filtered
        return papers[:limit]

    async def inspect_paper(self, paper_id: str) -> Optional[Paper]:
        """
        Fetches paper, merges OpenAlex citation metrics, and computes existing predicates.
        Supports arXiv IDs as well as 'openalex:W...' identifiers.
        """
        clean_id = paper_id.strip()
        if clean_id.startswith("openalex:") or clean_id.startswith("https://openalex.org/"):
            try:
                paper = await self.openalex.get_work_by_id(clean_id)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("OpenAlex inspect failed for %s: %s", clean_id, exc)
                return None
            if not paper:
                return None
        else:
            try:
                paper = await self.arxiv.get_paper_by_id(clean_id)
            except httpx.HTTPError as exc:
                logger.warning("arXiv lookup failed for %s (%s); trying DuckDB fallback", clean_id, exc)
                paper = None

            if not paper:
                # Fallback to DuckDB Parquet in worker thread so event loop is never blocked
                try:
                    paper = await asyncio.to_thread(self.duckdb_hf.query_paper_metadata_by_id, clean_id)
                except duckdb.Error as exc:
                    logger.warning("DuckDB fallback lookup failed for %s: %s", clean_id, exc)
                    paper = None
                if not paper:
                    return None

            # Fetch OpenAlex citation graph for arXiv papers
            try:
                work = await self.openalex.get_work_by_arxiv(clean_id)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("OpenAlex enrichment failed for %s: %s", clean_id, exc)
                work = None
            if work:
                paper.openalex_id = work.openalex_id
                paper.citations_count = work.cited_by_count
                if work.doi:
                    paper.doi = work.doi

        # Attach stored predicates (live cached only)
        stored_preds = self.store.get_paper_predicates(paper.id)
        paper.semantic_features.update(stored_preds)
        for pred_id in stored_preds:
            paper.semantic_sources[pred_id] = "live"

        return paper

    @staticmethod
    def _no_evidence_claim(claim_id: str, statement: str, paper_id: str) -> Claim:
        return Claim(
            id=claim_id,
            statement=statement,
            paper_id=paper_id,
            status="no_evidence",
            verification_probability=0.0,
            supporting_evidence=[],
            source="none",
            result_state="unsupported",
            document_id=paper_id,
        )

    async def verify_custom_claim(self, claim_statement: str, paper_id: str) -> Optional[Claim]:
        """
        Verifies a user or agent-provided claim against a specific paper's full abstract/text.
        Identifies the best matching evidence span with exact character offsets.
        """
        paper = await self.inspect_paper(paper_id)
        if not paper:
            return None

        spans = self.extract_evidence_spans(paper)
        claim_id = f"claim_{paper.id}_{int(time.time())}"
        if not spans:
            return self._no_evidence_claim(claim_id, claim_statement, paper.id)

        evidence = self.rank_evidence_spans(spans, claim_statement, top_k=1)[0]
        claim = Claim(
            id=claim_id,
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

        # Step 1: Broad discovery (with OpenAlex fallback)
        candidates = await self._search_with_fallback(query, max_results=max_candidates)

        # Step 2: Pre-RAG Semantic Screening
        gate_report = await self.gate.screen_papers(candidates, predicates)
        survivors = gate_report.surviving_papers

        # Step 3: Citation Graph Expansion & Enrichment for survivors
        for paper in survivors:
            if paper.provenance_source == "openalex" or paper.id.startswith("openalex:"):
                continue
            try:
                work = await self.openalex.get_work_by_arxiv(paper.id)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("OpenAlex enrichment failed for %s: %s", paper.id, exc)
                work = None
            if work:
                paper.openalex_id = work.openalex_id
                paper.citations_count = work.cited_by_count

        # Step 4: Verification of top-k query-relevant spans (only evaluated spans attached)
        verified_claims: List[Claim] = []
        for paper in survivors:
            spans = self.extract_evidence_spans(paper, query)
            if not spans:
                no_ev_claim = self._no_evidence_claim(
                    f"claim_{paper.id}_0",
                    f"Relevance evidence for '{query}' in '{paper.title}'",
                    paper.id,
                )
                paper.claims.append(no_ev_claim)
                verified_claims.append(no_ev_claim)
                continue

            top_spans = self.rank_evidence_spans(spans, query, top_k=2)
            for idx, span in enumerate(top_spans):
                claim_stmt = (
                    f"Relevance evidence for '{query}' in '{paper.title}': {span.text}"
                )
                claim = Claim(
                    id=f"claim_{paper.id}_{idx}",
                    statement=claim_stmt,
                    paper_id=paper.id,
                    document_id=paper.id
                )
                checked_claim = await self.verifier.verify_claim(claim, span)
                paper.claims.append(checked_claim)
                verified_claims.append(checked_claim)

        duration = round(time.perf_counter() - t0, 3)
        heuristic_evaluations = gate_report.heuristic_count + sum(
            1 for c in verified_claims if c.source == "heuristic"
        )
        warning = None
        if heuristic_evaluations > 0 or self.jev.is_simulated:
            warning = (
                "Results include unverified heuristic evaluations "
                "(TYPESAFE_API_KEY not set or Jev API unavailable). "
                "Do not treat heuristic outputs as verified claims."
            )

        return ResearchReport(
            query=query,
            total_candidates_found=len(candidates),
            surviving_papers_count=len(survivors),
            surviving_papers=survivors,
            rejection_reasons=gate_report.rejection_reasons,
            verified_claims=verified_claims,
            heuristic_evaluations=heuristic_evaluations,
            warning=warning,
            execution_duration_sec=duration
        )
