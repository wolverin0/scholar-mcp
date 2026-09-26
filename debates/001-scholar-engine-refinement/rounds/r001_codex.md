# Round 1 - Codex

**Position:** Keep DuckDB as the analytical foundation; prioritize truthful verification, bounded MCP access, and measured retrieval quality before adding vector infrastructure.

**Key Arguments & Proposals:**

- **P0—reconcile architecture with implementation.** The inspected checkout exposes `scholar_search`, `scholar_inspect`, and `scholar_research`; discovery uses arXiv. Research constructs generic relevance claims and checks only the first 500 abstract characters. The context describes a broader target than the implemented pipeline.
- **P0—make verification auditable.** Extract actual claims with exact evidence spans, document versions, and provenance. Return support, contradiction, insufficient evidence, or unavailable. Propagate heuristic/provider status through MCP; simulated scores must never qualify as scientific verification. Reject malformed responses rather than defaulting missing answers to 0.5.
- **P0—establish release gates.** Use held-out, expert-labeled claim/evidence pairs, including negation, numerical disagreement, missing context, and provider outages. Measure false-support rate, abstention, calibration, retrieval recall@K, and cost. Distinguish fixture success from authenticated API acceptance.
- **Storage:** Benchmark million-paper workloads at p50/p95 with cold/warm caches, concurrent readers, and ingestion. Treat 50ms as a scoped local-query target. DuckDB FTS requires explicit index refresh after changes; publish consistent data/index snapshots. [DuckDB FTS documentation](https://duckdb.org/docs/current/core_extensions/full_text_search)
- **Partitioning:** Start curated Parquet with coarse publication-year partitions, compact files, and workload-informed sorting. Keep raw source snapshots separately. Avoid author/MeSH partitions; compare pruning and cross-year scan costs before adding partition dimensions.
- **Semantic execution:** Initially use remote predicates with pooled connections, bounded concurrency, deadlines, and caches keyed by evidence hash, predicate version, and model version. Preserve conflicting findings; assess methods, population, endpoints, retractions, and study independence. Journal prestige cannot resolve contradictory evidence.
- **MCP:** Prefer typed filters, versioned views, snapshot-bound cursors, bounded excerpts, and explicitly requested graph expansion. Streaming alone does not limit context consumption. Optional SQL needs an isolated worker, constrained functions/views, disabled external access, locked configuration, and resource deadlines: even `SELECT` can read files. Treat retrieved text as untrusted data. [DuckDB security documentation](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview)

**Assumptions & Trade-offs:** A single-node deployment and batch freshness are initially acceptable. P1 adds hybrid retrieval only for demonstrated recall gaps. Defer local distillation, distributed storage, and autonomous conflict adjudication pending evidence.

**Risks & Failure Modes:** Stale indexes, duplicate preprint/publication evidence, premature semantic filtering, truncated passages, cache contamination, and heuristic fallback presented as confidence.

**What Would Change My Mind:** Reproducible benchmarks showing unacceptable lexical recall, unfixable latency/freshness limits, or a local model matching held-out verification quality with materially better privacy, cost, or offline availability.

**Confidence:** 89%
