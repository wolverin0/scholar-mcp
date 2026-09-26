# Round 2 - Claude

**Agreements:**
Both peers are right to keep DuckDB as the storage layer, to defer vector search and a local model until benchmarks justify them, and to keep raw SQL away from agents. Codex's main point is the most important one in this debate: the code doesn't yet do what the architecture describes. Right now `scholar_research` emits generic relevance claims checked against only the first 500 characters of each abstract. So verification is the P0, not a P2. I also agree with Codex on:
- **Bad provider responses:** reject them instead of silently defaulting to 0.5.
- **Heuristic scores:** mark fallback scores as heuristic all the way through the MCP response.
- **Partitioning:** partition by year only.

**Critique of Codex:**
1. **Label cost.** An expert-labeled held-out set is correct, but it has no size or budget, so it could quietly block every release. Start with about 200 adversarial claim/evidence pairs: negation, numeric mismatch, population mismatch, retracted work. Build them by hand from the existing arXiv fixtures, then grow the set from real disagreements seen in production.
2. **Index refresh.** DuckDB FTS rebuilds the whole index; it doesn't update incrementally. At a million papers, "explicit refresh" means a long rebuild that blocks writes. The concrete fix is two database files: rebuild into a shadow file, then atomically swap which file is live. The snapshot-bound cursors Codex proposes then come almost for free, because a cursor just records which file version it came from.
3. **Missing prerequisite.** Claim extraction with exact evidence spans needs full text, not abstracts. Codex never addresses how to get it: arXiv source/PDF licensing, parsing quality, and section segmentation. Without full text, "insufficient evidence" becomes the most common verdict and the release gates measure nothing useful.
4. **Remote predicates.** Remote calls on every candidate are expensive. Run cheap lexical and metadata filtering first so only the top-K reach the paid API.

**Critique of Gemini:**
1. **BM25 and meaning.** BM25 is not semantic search. Setting a 50ms target for "semantic" queries on BM25 mixes up two different problems.
2. **Partitioning by `source_id`.** With many sources this multiplies small files and hurts pruning on queries that span years.
3. **Venue heuristic.** "Prefer Nature over preprints, with a recency bias" is the dangerous part. Venue prestige does not tell you whether a claim is true. That heuristic would suppress valid replication failures and retraction signals. Contradictions should be returned as contradictions, with metadata on method, population and independence, not settled by rank.
4. **"Safe" queries.** A templated `safe_query` still needs DuckDB locked down: `enable_external_access=false`, `lock_configuration`, and no file-reading functions. Templates stop injection; they don't stop `read_csv('/etc/...')` if raw expressions leak in.
5. **Caching.** "Time-aware" caching is the wrong key. Cache entries should be keyed on the evidence hash, the predicate version and the model version, not on time-to-live.

**Defended / Refined Position:**
The P0 order is:
1. Honest verification status in every MCP response: supported, contradicted, insufficient, unavailable or heuristic.
2. A full-text ingestion path with evidence spans.
3. The ~200-pair adversarial eval, gated on false-support rate.
4. Blue/green FTS snapshots.
5. Typed MCP filters plus bounded excerpts.

Hybrid or vector retrieval should wait until recall@K on the eval shows a real lexical gap. Local distillation should wait until the remote API's cost or latency actually shows up in logs as a problem.

**Confidence:** 87%
