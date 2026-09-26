"""
OpenAlex Knowledge Graph Client.
Fetches citation graphs, author institutions, referenced works, and impact metrics.
"""

from __future__ import annotations
import httpx
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

OPENALEX_API_URL = "https://api.openalex.org"


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

    def __init__(self, mailto: str = "infra@homelab.local", timeout: float = 12.0):
        # OpenAlex requests a mailto in user-agent for polite pool
        self.headers = {"User-Agent": f"ScholarEngine/1.0 (mailto:{mailto})"}
        self.timeout = timeout

    async def get_work_by_arxiv(self, arxiv_id: str) -> Optional[OpenAlexWork]:
        """
        Retrieves OpenAlex work record for an arXiv ID.
        """
        clean_id = arxiv_id.replace("arxiv:", "").strip()
        # OpenAlex supports filter=locations.source.id or ids.arxiv
        url = f"{OPENALEX_API_URL}/works"
        params = {"filter": f"ids.arxiv:{clean_id}"}

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout) as client:
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
        # Clean ID e.g. https://openalex.org/W12345 -> W12345
        work_id = openalex_id.split("/")[-1]
        url = f"{OPENALEX_API_URL}/works/{work_id}"

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {"references": [], "cited_by": []}
            work_data = resp.json()
            refs = work_data.get("referenced_works", [])
            
            # Fetch a sample of works that cite this work
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
