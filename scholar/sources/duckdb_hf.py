"""
DuckDB Remote Hugging Face Parquet Query Engine.
Allows querying arxiv-complete (3.15M papers) via HTTP Range Requests without downloading 16 TB.
"""

from __future__ import annotations
import logging
import duckdb
from typing import List, Optional
from scholar.core.papers import Paper

logger = logging.getLogger(__name__)

HF_ARXIV_COMPLETE_BASE = "https://huggingface.co/datasets/secemp9/arxiv-complete/resolve/main"
DEFAULT_PARTITIONS = [
    f"{HF_ARXIV_COMPLETE_BASE}/data/metadata-0000{i}-of-00008.parquet"
    for i in range(8)
]


class DuckDBHuggingFaceClient:
    """
    Executes selective queries over Hugging Face Parquet partitions.
    Uses DuckDB's httpfs extension lazily for zero-download range queries.
    """

    def __init__(self, db_instance: Optional[duckdb.DuckDBPyConnection] = None):
        # Lazy connection & extension setup: never triggers network calls on import/init.
        self._db_instance = db_instance

    @staticmethod
    def _resolve_urls(
        parquet_url: Optional[str] = None,
        parquet_urls: Optional[List[str]] = None,
    ) -> List[str]:
        if parquet_urls is not None:
            return list(parquet_urls)
        if parquet_url is not None:
            return [parquet_url]
        return list(DEFAULT_PARTITIONS)

    @staticmethod
    def _ensure_httpfs(conn: duckdb.DuckDBPyConnection, urls: List[str]) -> None:
        if any(u.startswith(("http://", "https://")) for u in urls):
            try:
                conn.execute("INSTALL httpfs; LOAD httpfs;")
            except duckdb.Error as exc:
                # httpfs may already be loaded or statically linked; remote query will fail if unavailable.
                logger.debug("Skipping httpfs install/load: %s", exc)

    def _run_query(self, sql: str, params: list, urls: List[str], fetch_all: bool = False):
        own_conn = self._db_instance is None
        conn = duckdb.connect(":memory:") if own_conn else self._db_instance
        try:
            self._ensure_httpfs(conn, urls)
            cursor = conn.execute(sql, params)
            return cursor.fetchall() if fetch_all else cursor.fetchone()
        finally:
            if own_conn:
                conn.close()

    def query_paper_metadata_by_id(
        self,
        arxiv_id: str,
        parquet_url: Optional[str] = None,
        parquet_urls: Optional[List[str]] = None,
    ) -> Optional[Paper]:
        """
        Queries a specific paper across arxiv-complete metadata parquet partitions.
        Returns None if not found; raises duckdb.Error on read/schema failures.
        """
        clean_id = arxiv_id.replace("arxiv:", "").strip()
        urls = self._resolve_urls(parquet_url=parquet_url, parquet_urls=parquet_urls)

        query = """
            SELECT id, title, abstract, categories, authors, update_date
            FROM read_parquet(?)
            WHERE id = ?
            LIMIT 1
        """
        try:
            res = self._run_query(query, [urls, clean_id], urls, fetch_all=False)
        except duckdb.Error as exc:
            logger.warning("DuckDB query_paper_metadata_by_id failed for %s: %s", clean_id, exc)
            raise

        if not res:
            return None

        p_id, title, abstract, cats, _authors_raw, upd_date = res
        categories = cats.split() if isinstance(cats, str) else []
        return Paper(
            id=str(p_id),
            title=str(title).strip(),
            abstract=str(abstract).strip(),
            categories=categories,
            updated_date=str(upd_date) if upd_date else None,
            provenance_source="arxiv_complete_duckdb",
        )

    def search_metadata_by_category(
        self,
        category: str,
        limit: int = 10,
        parquet_url: Optional[str] = None,
        parquet_urls: Optional[List[str]] = None,
    ) -> List[Paper]:
        """
        Searches papers belonging to an exact category token (e.g. 'cs.NI', 'cs.AI') across partitions.
        Raises duckdb.Error on read/schema failures.
        """
        urls = self._resolve_urls(parquet_url=parquet_url, parquet_urls=parquet_urls)
        query = """
            SELECT id, title, abstract, categories, update_date
            FROM read_parquet(?)
            WHERE list_contains(string_split(coalesce(categories, ''), ' '), ?)
            LIMIT ?
        """
        try:
            rows = self._run_query(query, [urls, category.strip(), limit], urls, fetch_all=True)
        except duckdb.Error as exc:
            logger.warning("DuckDB search_metadata_by_category failed for %s: %s", category, exc)
            raise

        papers = []
        for r in rows:
            p_id, title, abstract, cats, upd_date = r
            papers.append(Paper(
                id=str(p_id),
                title=str(title).strip(),
                abstract=str(abstract).strip(),
                categories=str(cats).split() if cats else [],
                updated_date=str(upd_date) if upd_date else None,
                provenance_source="arxiv_complete_duckdb",
            ))
        return papers
