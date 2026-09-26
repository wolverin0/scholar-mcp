"""
Live arXiv API client.
Provides free, authoritative metadata and fresh search results via arXiv's export API.
"""

from __future__ import annotations
import xml.etree.ElementTree as ET
import httpx
from typing import List, Optional
from scholar.core.papers import Paper, Author

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivAPIClient:
    """
    Client for querying the official arXiv API.
    """

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def search(self, query: str, max_results: int = 10) -> List[Paper]:
        """
        Executes a search query against arXiv (title, abstract, categories).
        """
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending"
        }

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(ARXIV_API_URL, params=params)
            resp.raise_for_status()
            return self._parse_atom_feed(resp.text)

    async def get_paper_by_id(self, arxiv_id: str) -> Optional[Paper]:
        """
        Fetches an individual paper by its arXiv ID (e.g. '2401.12345').
        """
        clean_id = arxiv_id.replace("arxiv:", "").strip()
        params = {
            "id_list": clean_id,
            "max_results": 1
        }

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(ARXIV_API_URL, params=params)
            resp.raise_for_status()
            papers = self._parse_atom_feed(resp.text)
            return papers[0] if papers else None

    def _parse_atom_feed(self, xml_content: str) -> List[Paper]:
        root = ET.fromstring(xml_content)
        papers: List[Paper] = []

        for entry in root.findall("atom:entry", ATOM_NS):
            id_el = entry.find("atom:id", ATOM_NS)
            raw_id = id_el.text.strip() if id_el is not None else ""
            # Extract clean arXiv ID from URL like http://arxiv.org/abs/2401.12345v1
            paper_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id

            title_el = entry.find("atom:title", ATOM_NS)
            title = " ".join(title_el.text.strip().split()) if title_el is not None else "Untitled"

            summary_el = entry.find("atom:summary", ATOM_NS)
            abstract = " ".join(summary_el.text.strip().split()) if summary_el is not None else ""

            published_el = entry.find("atom:published", ATOM_NS)
            published_date = published_el.text.strip() if published_el is not None else None

            updated_el = entry.find("atom:updated", ATOM_NS)
            updated_date = updated_el.text.strip() if updated_el is not None else None

            # Authors
            authors: List[Author] = []
            for author_el in entry.findall("atom:author", ATOM_NS):
                name_el = author_el.find("atom:name", ATOM_NS)
                if name_el is not None and name_el.text:
                    authors.append(Author(name=name_el.text.strip()))

            # Categories
            categories: List[str] = []
            primary_cat = None
            primary_el = entry.find("arxiv:primary_category", ATOM_NS)
            if primary_el is not None:
                primary_cat = primary_el.attrib.get("term")

            for cat_el in entry.findall("atom:category", ATOM_NS):
                term = cat_el.attrib.get("term")
                if term:
                    categories.append(term)

            # PDF link
            pdf_url = None
            for link_el in entry.findall("atom:link", ATOM_NS):
                if link_el.attrib.get("title") == "pdf":
                    pdf_url = link_el.attrib.get("href")
                    break

            paper = Paper(
                id=paper_id,
                title=title,
                abstract=abstract,
                authors=authors,
                categories=categories,
                primary_category=primary_cat,
                published_date=published_date,
                updated_date=updated_date,
                pdf_url=pdf_url,
                provenance_source="arxiv_api"
            )
            papers.append(paper)

        return papers
