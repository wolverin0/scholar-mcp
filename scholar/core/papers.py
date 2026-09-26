"""
Data models for Scholar Engine.
Covers papers, authors, citations, semantic predicates, claims, and evidence.
"""

from __future__ import annotations
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class Author(BaseModel):
    name: str
    affiliation: Optional[str] = None
    orcid: Optional[str] = None


class Citation(BaseModel):
    source_paper_id: str
    target_paper_id: str
    context: Optional[str] = None
    relationship: Optional[str] = Field(
        default=None,
        description="Relationship type: extends, uses, compares_against, contradicts, replicates, applies"
    )


class Evidence(BaseModel):
    paper_id: str
    section: Optional[str] = None
    text: str
    figure_or_table: Optional[str] = None
    confidence: float = 1.0
    start_char: Optional[int] = Field(default=None, description="Exact start character offset in source text")
    end_char: Optional[int] = Field(default=None, description="Exact end character offset in source text")
    source_field: str = Field(default="abstract", description="Field source: abstract, conclusion, methods, full_text")
    doc_id: Optional[str] = None


class Claim(BaseModel):
    id: str
    statement: str
    paper_id: str
    status: str = Field(
        default="pending",
        description="Status: supported, partial, unsupported, contradicted"
    )
    verification_probability: Optional[float] = None
    supporting_evidence: List[Evidence] = Field(default_factory=list)
    source: str = Field(
        default="heuristic",
        description="Verification source: 'live' (real API / LLM) or 'heuristic' (local fallback)"
    )
    result_state: str = Field(
        default="heuristic",
        description="Result state: verified, heuristic, failed, contradicted, unsupported"
    )
    model_version: Optional[str] = None
    document_id: Optional[str] = None


class Paper(BaseModel):
    id: str = Field(description="Normalized identifier, e.g. arXiv ID '2401.12345'")
    title: str
    abstract: str
    authors: List[Author] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    primary_category: Optional[str] = None
    doi: Optional[str] = None
    published_date: Optional[str] = None
    updated_date: Optional[str] = None
    
    # Text and content representations (lazy loaded)
    full_text_tex: Optional[str] = None
    sections: Dict[str, str] = Field(default_factory=dict)
    pdf_url: Optional[str] = None
    
    # Knowledge & Semantic Index fields
    citations_count: int = 0
    openalex_id: Optional[str] = None
    semantic_features: Dict[str, float] = Field(
        default_factory=dict,
        description="Keyed by predicate name/id, value is probability [0.0, 1.0]"
    )
    claims: List[Claim] = Field(default_factory=list)
    
    # Metadata tracking
    provenance_source: str = Field(
        default="arxiv",
        description="Source: arxiv_api, arxiv_complete, openalex, cache"
    )
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def matches_predicates(self, thresholds: Dict[str, float]) -> bool:
        """
        Evaluates whether the paper meets all given predicate thresholds.
        thresholds: dict of {'predicate_name': min_probability}
        """
        for pred, min_prob in thresholds.items():
            current_prob = self.semantic_features.get(pred, 0.0)
            if current_prob < min_prob:
                return False
        return True
