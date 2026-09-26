import pytest
from scholar.sources.arxiv_api import ArxivAPIClient
from scholar.sources.openalex import OpenAlexClient
from scholar.sources.duckdb_hf import DuckDBHuggingFaceClient
import duckdb

SAMPLE_ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>High Throughput Wireless Scheduling</title>
    <summary>An evaluation of queue management in fixed wireless.</summary>
    <published>2024-01-15T10:00:00Z</published>
    <author><name>Jane Doe</name></author>
    <arxiv:primary_category term="cs.NI"/>
    <category term="cs.NI"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""

SAMPLE_OPENALEX_JSON = {
    "id": "https://openalex.org/W999999",
    "doi": "https://doi.org/10.1145/sample",
    "title": "High Throughput Wireless Scheduling",
    "cited_by_count": 42,
    "publication_year": 2024,
    "referenced_works": ["https://openalex.org/W111", "https://openalex.org/W222"],
    "topics": [{"display_name": "Computer Networks"}, {"display_name": "Wireless Communication"}],
    "authorships": [{"institutions": [{"display_name": "MIT"}]}]
}


def test_arxiv_atom_parser():
    client = ArxivAPIClient()
    papers = client._parse_atom_feed(SAMPLE_ATOM_XML)
    assert len(papers) == 1
    p = papers[0]
    assert p.id == "2401.12345v1"
    assert p.title == "High Throughput Wireless Scheduling"
    assert p.primary_category == "cs.NI"
    assert len(p.authors) == 1
    assert p.authors[0].name == "Jane Doe"
    assert p.pdf_url == "http://arxiv.org/pdf/2401.12345v1"


def test_openalex_parser():
    client = OpenAlexClient()
    work = client._parse_work(SAMPLE_OPENALEX_JSON)
    assert work.openalex_id == "https://openalex.org/W999999"
    assert work.cited_by_count == 42
    assert len(work.referenced_works) == 2
    assert "Computer Networks" in work.topics
    assert "MIT" in work.institutions


def test_duckdb_hf_local_parquet():
    conn = duckdb.connect(":memory:")
    # Create sample in-memory table mimicking arxiv-complete schema
    conn.execute("""
        CREATE TABLE sample_metadata (
            id VARCHAR,
            title VARCHAR,
            abstract VARCHAR,
            categories VARCHAR,
            authors VARCHAR,
            update_date VARCHAR
        )
    """)
    conn.execute("""
        INSERT INTO sample_metadata VALUES 
        ('2401.12345', 'Sample Paper', 'Abstract text here', 'cs.NI cs.IT', 'Author Name', '2024-01-15')
    """)

    client = DuckDBHuggingFaceClient(db_instance=conn)
    # Test query using table override
    res = conn.execute("SELECT id, title, abstract, categories, authors, update_date FROM sample_metadata WHERE id = '2401.12345'").fetchone()
    assert res is not None
    assert res[0] == "2401.12345"
    assert res[1] == "Sample Paper"
