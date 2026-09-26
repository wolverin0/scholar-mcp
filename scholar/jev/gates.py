"""
Pre-RAG and Post-RAG Semantic Gates.
Pre-RAG: Filters candidates using high-speed probabilistic predicate evaluations.
Post-RAG: Evaluates generated claims against cited evidence text to eliminate hallucinations.
"""

from __future__ import annotations
from typing import List, Dict, Tuple, Optional
from pydantic import BaseModel, Field
from scholar.core.papers import Paper, Claim, Evidence
from scholar.core.predicates import SemanticPredicate, PredicateResult, PredicateStore
from scholar.jev.client import JevClient


class GateEvaluationReport(BaseModel):
    total_candidates: int
    passed_count: int
    rejected_count: int
    surviving_papers: List[Paper]
    rejection_reasons: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Keyed by paper_id, list of failed predicate reasons"
    )


class PreRAGGate:
    """
    Discriminates candidate papers before expensive full-text retrieval or LLM reasoning.
    """

    def __init__(self, jev_client: JevClient, store: Optional[PredicateStore] = None):
        self.jev = jev_client
        self.store = store or PredicateStore()

    async def screen_papers(
        self,
        papers: List[Paper],
        predicates: List[SemanticPredicate]
    ) -> GateEvaluationReport:
        survivors: List[Paper] = []
        rejections: Dict[str, List[str]] = {}

        for paper in papers:
            paper_passed = True
            reasons: List[str] = []

            for pred in predicates:
                # Check if result is already in store/cache
                cached = self.store.get_result(pred.id, paper.id)
                if cached:
                    prob = cached.probability
                else:
                    # Evaluate via Jev against abstract + title
                    state_text = f"Title: {paper.title}\n\nAbstract: {paper.abstract}"
                    decision = await self.jev.evaluate_noul(state_text, pred.question)
                    prob = decision.probability
                    
                    # Cache in store
                    self.store.record_result(PredicateResult(
                        predicate_id=pred.id,
                        paper_id=paper.id,
                        probability=prob,
                        latency_ms=decision.latency_ms,
                        model=decision.model_version
                    ))

                # Update paper model features
                paper.semantic_features[pred.id] = prob

                # Check against threshold
                if prob < pred.default_threshold:
                    paper_passed = False
                    reasons.append(
                        f"Failed {pred.id} ({pred.question[:40]}...): P={prob:.2f} < threshold={pred.default_threshold:.2f}"
                    )

            if paper_passed:
                survivors.append(paper)
            else:
                rejections[paper.id] = reasons

        return GateEvaluationReport(
            total_candidates=len(papers),
            passed_count=len(survivors),
            rejected_count=len(rejections),
            surviving_papers=survivors,
            rejection_reasons=rejections
        )


class PostRAGVerifier:
    """
    Verifies that reasoning claims are genuinely supported by cited text.
    Prevents hallucinations from reaching production reports.
    """

    def __init__(self, jev_client: JevClient):
        self.jev = jev_client

    async def verify_claim(self, claim: Claim, cited_evidence: Evidence) -> Claim:
        state_text = f"EVIDENCE PASSAGE:\n\"{cited_evidence.text}\"\n\nCLAIM TO VERIFY:\n\"{claim.statement}\""
        
        # Question 1: Is the claim directly supported?
        support_q = "Is the claim directly and truthfully supported by the evidence passage without extrapolation?"
        decision = await self.jev.evaluate_noul(state_text, support_q)
        prob = decision.probability
        claim.verification_probability = prob
        claim.source = decision.source
        claim.model_version = decision.model_version
        claim.document_id = cited_evidence.paper_id or claim.paper_id

        if prob >= 0.80:
            claim.status = "supported"
            claim.result_state = "verified" if decision.source == "live" else "heuristic"
        elif prob >= 0.50:
            claim.status = "partial"
            claim.result_state = "verified" if decision.source == "live" else "heuristic"
        else:
            # Question 2: Is it actively contradicted?
            contra_q = "Does the evidence passage contradict or refute the claim?"
            contra_decision = await self.jev.evaluate_noul(state_text, contra_q)
            if contra_decision.probability >= 0.70:
                claim.status = "contradicted"
                claim.result_state = "contradicted"
            else:
                claim.status = "unsupported"
                claim.result_state = "unsupported"

        claim.supporting_evidence.append(cited_evidence)
        return claim
