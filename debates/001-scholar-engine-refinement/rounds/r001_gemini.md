# Round 1 - Gemini

**Position:** Prioritize robust DuckDB native capabilities and agent safety with controlled API access, deferring complex vector search and local SLM until empirical performance bottlenecks are unequivocally demonstrated.

**Key Arguments & Proposals:**
*   **Storage & Query Optimization:** Leverage DuckDB's native BM25 and columnar filtering. Optimize Parquet partitioning by `publication_year` and `source_id` for common cross-corpus queries. Defer embedded vector engines; only integrate if sub-50ms latency for *semantic* similarity beyond keywords proves unattainable on production scale.
*   **Semantic Predicates & Claim-Evidence Verification:** Utilize TypeSafe API with aggressive, time-aware local caching for predicate results. Implement a simple, configurable heuristic for conflicting claims: prefer peer-reviewed sources (e.g., Nature) over preprints (e.g., bioRxiv), with a recency bias. Defer local ONNX/distilled SLM runtime; this is a significant engineering investment.
*   **MCP Surface & Agent Ergonomics:** **Reject raw `query_duckdb` SQL access for LLM agents.** Implement a `safe_query` endpoint using a templated query builder or allow-list to prevent injection and schema drift. Introduce pagination/streaming for large abstract and citation graph payloads to prevent context window blowout.
*   **Implementation Priorities (P0):** Refine `search_papers` and `get_paper_details` performance. Implement robust local caching for TypeSafe API. Develop the `safe_query` endpoint. Implement basic conflicting claim resolution.
*   **Rejected as Premature:** Immediate integration of vector DBs, local SLM runtime, complex graph databases, or custom distributed query engines.

**Assumptions & Trade-offs:**
*   **Assumptions:** DuckDB's native indexing and columnar performance will meet initial *keyword/metadata* search latency requirements. TypeSafe API is sufficiently reliable and cost-effective for initial predicate scaling.
*   **Trade-offs:** Potentially higher initial API costs. Less immediate "deep semantic" search without vectors. Agents have less direct SQL flexibility, requiring more structured query patterns.

**Risks & Failure Modes:**
*   DuckDB's BM25 performance may not scale adequately for millions of papers, necessitating a costly, late-stage vector integration.
*   TypeSafe API latency or cost could become prohibitive sooner than anticipated, forcing an urgent pivot to local SLM.
*   The `safe_query` endpoint might be too restrictive, hindering advanced agent data exploration capabilities.
*   Simple conflicting claim heuristics might lead to unacceptable verification inaccuracies.

**What Would Change My Mind:**
*   Empirical benchmarks showing DuckDB BM25 consistently failing sub-50ms latency targets for *semantic* queries on production-scale datasets, even after query optimization.
*   Documented TypeSafe API instability, significant pricing changes, or sustained high latency proving it non-viable for core operations.
*   Agent performance metrics demonstrating critical failure modes directly attributable to `safe_query` limitations that cannot be addressed by new, controlled API endpoints.

**Confidence:** 85%
