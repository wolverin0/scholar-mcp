"""
DuckDB Remote Hugging Face Parquet Query Engine.
Allows querying arxiv-complete (3.15M papers) via HTTP Range Requests without downloading 16 TB.
"""

from __future__ import annotations
import duckdb
from typing import Dict, List, Optional, Any
from scholar.core.papers import Paper, Author

HF_ARXIV_COMPLETE_BASE = "https://huggingface.co/datasets/secemp9/arxiv-complete/resolve/main"


class DuckDBHuggingFaceClient:
    """
    Executes selective queries over Hugging Face Parquet partitions.
    Uses DuckDB's httpfs extension for zero-download range queries.
    """

    def __init__(self, db_instance: Optional[duckdb.DuckDBPyConnection] = None):
        self.conn = db_instance or duckdb.connect(":memory:")
        self._setup_extensions()

    def _setup_extensions(self):
        try:
            self.conn.execute("INSTALL httpfs; LOAD httpfs;")
        except Exception:
            # httpfs might already be statically linked in pre-built binary
            pass

    def query_paper_metadata_by_id(self, arxiv_id: str, parquet_url: Optional[str] = None) -> Optional[Paper]:
        """
        Queries a specific paper from arxiv-complete metadata parquet.
        """
        clean_id = arxiv_id.replace("arxiv:", "").strip()
        url = parquet_url or f"{HF_ARXIV_COMPLETE_BASE}/data/metadata-00000-of-00008.parquet"
        
        query = """
            SELECT id, title, abstract, categories, authors, update_date
            FROM read_parquet(?)
            WHERE id = ?
            LIMIT 1
        """
        try:
            res = self.conn.execute(query, [url, clean_id]).fetchone()
            if not res:
                return None
            
            p_id, title, abstract, cats, authors_raw, upd_date = res
            categories = cats.split() if isinstance(cats, str) else []
            
            return Paper(
                id=str(p_id),
                title=str(title).strip(),
                abstract=str(abstract).strip(),
                categories=categories,
                updated_date=str(upd_date) if upd_date else None,
                provenance_source="arxiv_complete_duckdb"
            )
        except Exception as e:
            # Network or schema error
            return None

    def search_metadata_by_category(self, category: str, limit: int = 10, parquet_url: Optional[str] = None) -> List[Paper]:
        """
        Searches papers belonging to a category (e.g. 'cs.NI', 'cs.AI') in metadata partition.
        """
        url = parquet_url or f"{HF_ARXIV_COMPLETE_BASE}/data/metadata-00000-of-00008.parquet"
        query = """
            SELECT id, title, abstract, categories, update_date
            FROM read_parquet(?)
            WHERE categories LIKE ?
            LIMIT ?
        """
        try:
            rows = self.conn.execute(query, [url, f"%{category}%", limit]).fetchall()
            papers = []
            for r in rows:
                p_id, title, abstract, cats, upd_date = r
                papers.append(Paper(
                    id=str(p_id),
                    title=str(title).strip(),
                    abstract=str(abstract).strip(),
                    categories=str(cats).split() if cats else [],
                    updated_date=str(upd_date) if upd_date else None,
                    provenance_source="arxiv_complete_duckdb"
                ))
            return papers
        except Exception:
            return []
