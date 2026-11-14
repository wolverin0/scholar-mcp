"""
OpenAlex Knowledge Graph Client.
Fetches citation graphs, author institutions, referenced works, and impact metrics.
"""

from __future__ import annotations
import logging
import re
import httpx
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from scholar.core.papers import Author, Paper

logger = logging.getLogger(__name__)

OPENALEX_API_URL = "https://api.openalex.org"
_ARXIV_ID_RE = re.compile(
    r"^(?:\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[a-z-]+)?/\d{7}(?:v\d+)?)$",
    re.IGNORECASE,
)
_OPENALEX_WORK_ID_RE = re.compile(r"^W\d+$", re.IGNORECASE)


class OpenAlexWork(BaseModel):
    openalex_id: str
    doi: Optional[str] = None
    title: str
    cited_by_count: int = 0
    publication_year: Optional[int] = None
    referenced_works: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    institutions: List[str] = Field(default_factory=list)


class OpenAlexClient:
    """
    Client for querying OpenAlex scholarly knowledge graph.
    """

    def __init__(
        self,
        mailto: str = "infra@homelab.local",
        timeout: float = 12.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        # OpenAlex requests a mailto in user-agent for polite pool
        self.headers = {"User-Agent": f"ScholarEngine/1.0 (mailto:{mailto})"}
        self.timeout = timeout
        self.transport = transport

    def _make_http_client(self) -> httpx.AsyncClient:
        if self.transport is not None:
            return httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                transport=self.transport,
            )
        return httpx.AsyncClient(headers=self.headers, timeout=self.timeout)

    @staticmethod
    def _reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> str:
        if not inverted_index or not isinstance(inverted_index, dict):
            return ""
        positions: Dict[int, str] = {}
        for word, indices in inverted_index.items():
            if not isinstance(indices, list):
                continue
            for pos in indices:
                if isinstance(pos, int):
                    positions[pos] = word
        if not positions:
            return ""
        return " ".join(positions[i] for i in sorted(positions))

    def _work_item_to_paper(self, item: Dict[str, Any]) -> Paper:
        raw_oa_id = item.get("id", "")
        short_oa_id = raw_oa_id.split("/")[-1] if raw_oa_id else ""
        ids = item.get("ids") or {}
        arxiv_url = ids.get("arxiv") if isinstance(ids, dict) else None
        if arxiv_url and "/abs/" in str(arxiv_url):
            paper_id = str(arxiv_url).split("/abs/")[-1]
        elif short_oa_id:
            paper_id = f"openalex:{short_oa_id}"
        else:
            paper_id = "openalex:unknown"

        authors: List[Author] = []
        for authorship in item.get("authorships", []):
            author_obj = authorship.get("author") or {}
            name = author_obj.get("display_name")
            if name:
                authors.append(Author(name=name))

        topics: List[str] = []
        for t in item.get("topics", []):
            name = t.get("display_name")
            if name:
                topics.append(name)

        pub_date = item.get("publication_date")
        if not pub_date and item.get("publication_year"):
            pub_date = str(item["publication_year"])

        return Paper(
            id=paper_id,
            title=(item.get("title") or "Untitled").strip(),
            abstract=self._reconstruct_abstract(item.get("abstract_inverted_index")),
            authors=authors,
            categories=topics,
            doi=item.get("doi"),
            published_date=pub_date,
            citations_count=item.get("cited_by_count", 0) or 0,
            openalex_id=raw_oa_id or None,
            provenance_source="openalex",
        )

    async def search_works(self, query: str, limit: int = 10) -> List[Paper]:
        """
        Searches OpenAlex works by query string and returns Paper objects with provenance_source='openalex'.
        """
        url = f"{OPENALEX_API_URL}/works"
        params = {"search": query, "per-page": limit}
        async with self._make_http_client() as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
            return [self._work_item_to_paper(item) for item in data.get("results", [])]

    async def get_work_by_id(self, openalex_id: str) -> Optional[Paper]:
        """
        Retrieves a single OpenAlex work by ID (e.g. 'openalex:W12345', 'W12345', or full URL).
        """
        clean_id = openalex_id.strip()
        if clean_id.startswith("openalex:"):
            clean_id = clean_id[len("openalex:"):]
        if "/" in clean_id:
            clean_id = clean_id.split("/")[-1]
        if not _OPENALEX_WORK_ID_RE.match(clean_id):
            raise ValueError(f"Invalid OpenAlex work ID: {openalex_id!r}")

        url = f"{OPENALEX_API_URL}/works/{clean_id}"
        async with self._make_http_client() as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            return self._work_item_to_paper(resp.json())

    async def get_work_by_arxiv(self, arxiv_id: str) -> Optional[OpenAlexWork]:
        """
        Retrieves OpenAlex work record for an arXiv ID.
        """
        clean_id = arxiv_id.replace("arxiv:", "").strip()
        if not _ARXIV_ID_RE.match(clean_id):
            raise ValueError(f"Invalid arXiv ID for OpenAlex lookup: {arxiv_id!r}")

        url = f"{OPENALEX_API_URL}/works"
        params = {"filter": f"ids.arxiv:{clean_id}"}

        async with self._make_http_client() as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            results = data.get("results", [])
            if not results:
                return None
            return self._parse_work(results[0])

    async def get_citation_graph(self, openalex_id: str) -> Dict[str, Any]:
        """
        Fetches both referenced works (predecessors) and citing works (successors).
        """
        work_id = openalex_id.split("/")[-1]
        url = f"{OPENALEX_API_URL}/works/{work_id}"

        async with self._make_http_client() as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {"references": [], "cited_by": []}
            work_data = resp.json()
            refs = work_data.get("referenced_works", [])

            cites_url = f"{OPENALEX_API_URL}/works"
            cites_params = {"filter": f"cites:{work_id}", "per-page": 10}
            cites_resp = await client.get(cites_url, params=cites_params)
            citing_works = []
            if cites_resp.status_code == 200:
                c_data = cites_resp.json()
                for c in c_data.get("results", []):
                    citing_works.append({
                        "id": c.get("id"),
                        "title": c.get("title"),
                        "year": c.get("publication_year"),
                        "cited_by_count": c.get("cited_by_count")
                    })

            return {
                "references": refs,
                "cited_by": citing_works
            }

    def _parse_work(self, item: Dict[str, Any]) -> OpenAlexWork:
        topics = []
        for t in item.get("topics", []):
            name = t.get("display_name")
            if name:
                topics.append(name)

        institutions = []
        for authorship in item.get("authorships", []):
            for inst in authorship.get("institutions", []):
                iname = inst.get("display_name")
                if iname and iname not in institutions:
                    institutions.append(iname)

        return OpenAlexWork(
            openalex_id=item.get("id", ""),
            doi=item.get("doi"),
            title=item.get("title", "Untitled"),
            cited_by_count=item.get("cited_by_count", 0),
            publication_year=item.get("publication_year"),
            referenced_works=item.get("referenced_works", []),
            topics=topics,
            institutions=institutions
        )
