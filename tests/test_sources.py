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


def test_duckdb_hf_constructor_is_lazy_no_httpfs():
    class SpyConn:
        def __init__(self):
            self.calls = []

        def execute(self, *args, **kwargs):
            self.calls.append(args[0])
            return self

    spy = SpyConn()
    DuckDBHuggingFaceClient(db_instance=spy)
    assert spy.calls == []


def test_duckdb_hf_queries_multiple_local_partitions(tmp_path):
    p1 = tmp_path / "metadata-00000-of-00002.parquet"
    p2 = tmp_path / "metadata-00001-of-00002.parquet"

    setup = duckdb.connect(":memory:")
    setup.execute(
        f"COPY (SELECT '2401.0001' AS id, 'First' AS title, 'Abs 1' AS abstract, "
        f"'cs.AIC' AS categories, 'Alice' AS authors, '2024-01-01' AS update_date) "
        f"TO '{p1.as_posix()}' (FORMAT PARQUET)"
    )
    setup.execute(
        f"COPY (SELECT '2401.0002' AS id, 'Second' AS title, 'Abs 2' AS abstract, "
        f"'cs.AI cs.LG' AS categories, 'Bob' AS authors, '2024-01-02' AS update_date) "
        f"TO '{p2.as_posix()}' (FORMAT PARQUET)"
    )
    setup.close()

    client = DuckDBHuggingFaceClient()
    paper = client.query_paper_metadata_by_id("2401.0002", parquet_urls=[str(p1), str(p2)])
    assert paper is not None
    assert paper.id == "2401.0002"
    assert paper.title == "Second"
    assert paper.provenance_source == "arxiv_complete_duckdb"

    # Not found returns None
    assert client.query_paper_metadata_by_id("9999.9999", parquet_urls=[str(p1), str(p2)]) is None

    # Token-aware category match: 'cs.AI' must match p2 ('cs.AI cs.LG'), not p1 ('cs.AIC')
    cat_papers = client.search_metadata_by_category("cs.AI", parquet_urls=[str(p1), str(p2)])
    assert [p.id for p in cat_papers] == ["2401.0002"]


def test_duckdb_hf_raises_on_read_error_instead_of_returning_none(tmp_path):
    missing = tmp_path / "does-not-exist.parquet"
    client = DuckDBHuggingFaceClient()
    with pytest.raises(duckdb.Error):
        client.query_paper_metadata_by_id("2401.0001", parquet_urls=[str(missing)])


@pytest.mark.live
def test_duckdb_hf_live_partition_schema():
    client = DuckDBHuggingFaceClient()
    # Verifies the remote Hugging Face parquet partition schema is readable
    res = client.search_metadata_by_category("cs.NI", limit=1)
    assert isinstance(res, list)


@pytest.mark.asyncio
async def test_openalex_search_works_sets_provenance_and_reconstructs_abstract():
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W4242",
                        "doi": "https://doi.org/10.1000/test",
                        "title": "OpenAlex Wireless Study",
                        "cited_by_count": 17,
                        "publication_year": 2025,
                        "abstract_inverted_index": {"Loaded": [0], "latency": [1], "improves.": [2]},
                        "authorships": [{"author": {"display_name": "Ada Lovelace"}, "institutions": []}],
                        "topics": [{"display_name": "Wireless Networks"}],
                    }
                ]
            },
        )

    client = OpenAlexClient(transport=httpx.MockTransport(handler))
    papers = await client.search_works("loaded latency", limit=5)
    assert len(papers) == 1
    assert papers[0].id == "openalex:W4242"
    assert papers[0].provenance_source == "openalex"
    assert papers[0].abstract == "Loaded latency improves."
    assert papers[0].citations_count == 17


def test_openalex_client_mailto_env_and_omission(monkeypatch):
    monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
    client_no_mail = OpenAlexClient()
    assert client_no_mail.headers["User-Agent"] == "ScholarEngine/1.0"
    assert "mailto:" not in client_no_mail.headers["User-Agent"]

    monkeypatch.setenv("OPENALEX_MAILTO", "research@example.org")
    client_env = OpenAlexClient()
    assert client_env.headers["User-Agent"] == "ScholarEngine/1.0 (mailto:research@example.org)"
