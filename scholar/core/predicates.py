"""
Semantic Predicate Registry and Cache.
Enables compiling natural language questions into reusable, probabilistic indexes.
"""

from __future__ import annotations
import sqlite3
import json
from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class SemanticPredicate(BaseModel):
    id: str = Field(description="Unique predicate key, e.g. 'P_real_hardware' or 'P_loaded_latency'")
    question: str = Field(description="The precise prompt or question evaluated by Jev System One")
    domain: Optional[str] = Field(default="general", description="Domain: wireless, agents, ai, databases")
    default_threshold: float = Field(default=0.75, description="Recommended filtering threshold")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PredicateResult(BaseModel):
    predicate_id: str
    paper_id: str
    probability: float
    confidence: Optional[float] = 1.0
    model: str = "jev-system-one"
    latency_ms: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PredicateStore:
    """
    SQLite-backed persistent store for semantic predicates and results.
    Acts as the materialized semantic bitmap cache.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        if self.db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
        else:
            self._mem_conn = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predicates (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                domain TEXT,
                default_threshold REAL,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predicate_results (
                predicate_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                probability REAL NOT NULL,
                confidence REAL,
                model TEXT,
                latency_ms REAL,
                created_at TEXT,
                PRIMARY KEY (predicate_id, paper_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_res_paper ON predicate_results(paper_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_res_prob ON predicate_results(predicate_id, probability)")
        conn.commit()

    def register_predicate(self, predicate: SemanticPredicate) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO predicates (id, question, domain, default_threshold, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (predicate.id, predicate.question, predicate.domain, predicate.default_threshold, predicate.created_at.isoformat()))
            conn.commit()

    def get_predicate(self, pred_id: str) -> Optional[SemanticPredicate]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM predicates WHERE id = ?", (pred_id,)).fetchone()
            if not row:
                return None
            return SemanticPredicate(
                id=row["id"],
                question=row["question"],
                domain=row["domain"],
                default_threshold=row["default_threshold"],
                created_at=datetime.fromisoformat(row["created_at"])
            )

    def record_result(self, result: PredicateResult) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO predicate_results (predicate_id, paper_id, probability, confidence, model, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (result.predicate_id, result.paper_id, result.probability, result.confidence, result.model, result.latency_ms, result.created_at.isoformat()))
            conn.commit()

    def get_result(self, pred_id: str, paper_id: str) -> Optional[PredicateResult]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM predicate_results WHERE predicate_id = ? AND paper_id = ?",
                (pred_id, paper_id)
            ).fetchone()
            if not row:
                return None
            return PredicateResult(
                predicate_id=row["predicate_id"],
                paper_id=row["paper_id"],
                probability=row["probability"],
                confidence=row["confidence"],
                model=row["model"],
                latency_ms=row["latency_ms"],
                created_at=datetime.fromisoformat(row["created_at"])
            )

    def get_paper_predicates(self, paper_id: str) -> Dict[str, float]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT predicate_id, probability FROM predicate_results WHERE paper_id = ?",
                (paper_id,)
            ).fetchall()
            return {r["predicate_id"]: r["probability"] for r in rows}

    def filter_papers_by_threshold(self, pred_id: str, min_prob: float) -> List[str]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT paper_id FROM predicate_results WHERE predicate_id = ? AND probability >= ?",
                (pred_id, min_prob)
            ).fetchall()
            return [r["paper_id"] for r in rows]
