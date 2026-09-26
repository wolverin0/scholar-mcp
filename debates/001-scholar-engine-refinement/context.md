# Debate Context: Scholar Engine & MCP Refinement Roadmap

## Project Overview
**Scholar Engine & MCP** (`https://github.com/wolverin0/scholar-mcp`) is a Python 3.12+ academic research infrastructure designed for autonomous coding agents and human researchers. It bridges high-throughput scientific ingestion with local analytics and sub-symbolic semantic verification.

### Core Stack
1. **Multi-Source Fetchers:** Ingestion from OpenAlex, Europe PMC, arXiv, bioRxiv/medRxiv, PubMed, and ClinicalTrials.gov.
2. **Analytical Store (DuckDB):** In-memory and persisted DuckDB (`scholar.duckdb`) providing native SQL, BM25 full-text indexing, Parquet partitioning, and columnar range scans across authors, citation counts, publication years, and MeSH terms.
3. **Semantic System One Verification (Jev / TypeSafe):** Integrated client for TypeSafe AI (`POST https://api.typesafe.ai/v1/systemone`) executing sub-symbolic boolean/probabilistic predicates over academic claims (e.g., `is_mechanistic_claim`, `has_quantitative_metrics`, `is_reproducible_methodology`), backed by local heuristic fallback.
4. **FastMCP Server (`scholar-mcp`):** Standard Model Context Protocol server exposing `search_papers`, `get_paper_details`, `query_duckdb`, `validate_claim_predicate`, `verify_claim_evidence`, and `export_parquet`.

---

## Key Debated Questions

### 1. Storage & Query Optimization (Columnar vs Hybrid Vector)
- Can DuckDB's native BM25 + columnar range filtering handle millions of papers with sub-50ms latency, or must we integrate an embedded vector engine (e.g. LanceDB / DuckDB-VSS)?
- What is the optimal partitioning scheme for Parquet data lakes when agents run cross-corpus queries?

### 2. Semantic Predicates & Claim-Evidence Verification
- How should Jev System One semantic predicates be scaled? Should agents use remote TypeSafe API calls with local cache, or should we build a local ONNX/distilled SLM runtime for offline predicate evaluation?
- How should conflicting claims (e.g., bioRxiv preprint vs peer-reviewed Nature paper) be weighted and reconciled in automated claim-evidence extraction?

### 3. MCP Surface & Agent Ergonomics
- Balancing SQL flexibility vs agent safety: Should LLM agents be given raw `query_duckdb` SQL access, or does that lead to schema drift and prompt injection risks?
- Preventing context window blowout: Best strategies for streaming large paper abstracts and citation graphs to orchestrating agents.

### 4. Implementation Priorities & Phasing
- What are the absolute P0 items for the next release?
- What architectural ideas should be strictly rejected as premature over-engineering?
