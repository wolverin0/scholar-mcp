"""
Semantic Predicate Registry and Cache.
Enables compiling natural language questions into reusable, probabilistic indexes.
"""

from __future__ import annotations
import hashlib
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


def hash_question(question: str) -> str:
    """Returns a deterministic hash prefix for a predicate question string."""
    return hashlib.sha256(question.strip().encode("utf-8")).hexdigest()[:16]


class SemanticPredicate(BaseModel):
    id: str = Field(description="Unique predicate key, e.g. 'P_real_hardware' or 'P_loaded_latency'")
    question: str = Field(description="The precise prompt or question evaluated by Jev System One")
    domain: Optional[str] = Field(default="general", description="Domain: wireless, agents, ai, databases")
    default_threshold: float = Field(default=0.75, description="Recommended filtering threshold")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PredicateResult(BaseModel):
    predicate_id: str
    paper_id: str
    probability: float
    question_hash: str = ""
    confidence: Optional[float] = 1.0
    model: str = "jev-system-one"
    source: str = Field(default="live", description="'live' or 'heuristic'")
    latency_ms: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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

    def _create_results_table(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predicate_results (
                predicate_id TEXT NOT NULL,
                question_hash TEXT NOT NULL DEFAULT '',
                paper_id TEXT NOT NULL,
                probability REAL NOT NULL,
                confidence REAL,
                model TEXT,
                source TEXT NOT NULL DEFAULT 'live',
                latency_ms REAL,
                created_at TEXT,
                PRIMARY KEY (predicate_id, question_hash, paper_id)
            )
        """)

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
        existing_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(predicate_results)").fetchall()
        }
        if not existing_cols:
            self._create_results_table(conn)
        elif "question_hash" not in existing_cols or "source" not in existing_cols:
            # Migrate legacy (predicate_id, paper_id) schema without losing existing rows.
            conn.execute("ALTER TABLE predicate_results RENAME TO predicate_results_legacy")
            self._create_results_table(conn)
            conn.execute("""
                INSERT INTO predicate_results (
                    predicate_id, question_hash, paper_id, probability,
                    confidence, model, source, latency_ms, created_at
                )
                SELECT
                    predicate_id,
                    '',
                    paper_id,
                    probability,
                    confidence,
                    model,
                    CASE
                        WHEN lower(coalesce(model, '')) LIKE '%simulated%' THEN 'heuristic'
                        ELSE 'live'
                    END,
                    latency_ms,
                    created_at
                FROM predicate_results_legacy
            """)
            conn.execute("DROP TABLE predicate_results_legacy")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_res_paper ON predicate_results(paper_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_res_prob ON predicate_results(predicate_id, probability)")
        conn.commit()
        if self._mem_conn is None:
            conn.close()

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
                INSERT OR REPLACE INTO predicate_results (
                    predicate_id, question_hash, paper_id, probability,
                    confidence, model, source, latency_ms, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.predicate_id,
                result.question_hash,
                result.paper_id,
                result.probability,
                result.confidence,
                result.model,
                result.source,
                result.latency_ms,
                result.created_at.isoformat(),
            ))
            conn.commit()

    def get_result(
        self,
        pred_id: str,
        paper_id: str,
        question: Optional[str] = None,
    ) -> Optional[PredicateResult]:
        q_hash = hash_question(question) if question is not None else ""
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM predicate_results
                WHERE predicate_id = ? AND question_hash = ? AND paper_id = ? AND source = 'live'
                """,
                (pred_id, q_hash, paper_id),
            ).fetchone()
            if not row:
                return None
            return PredicateResult(
                predicate_id=row["predicate_id"],
                question_hash=row["question_hash"],
                paper_id=row["paper_id"],
                probability=row["probability"],
                confidence=row["confidence"],
                model=row["model"],
                source=row["source"],
                latency_ms=row["latency_ms"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )

    def get_paper_predicates(self, paper_id: str) -> Dict[str, float]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT predicate_id, probability FROM predicate_results WHERE paper_id = ? AND source = 'live'",
                (paper_id,)
            ).fetchall()
            return {r["predicate_id"]: r["probability"] for r in rows}

    def filter_papers_by_threshold(self, pred_id: str, min_prob: float) -> List[str]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT paper_id FROM predicate_results WHERE predicate_id = ? AND probability >= ? AND source = 'live'",
                (pred_id, min_prob)
            ).fetchall()
            return [r["paper_id"] for r in rows]
