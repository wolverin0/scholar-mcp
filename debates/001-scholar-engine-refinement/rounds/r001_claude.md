# Round 1 - Claude

**Position:** Ground the roadmap in the code as it exists. Close the gaps between the docs and the code, and make it measurable, before adding vector engines or a local SLM runtime.

**Key Arguments & Proposals:**
- **The context doesn't match the repo.** The repo is about 1.5k LOC. `scholar/mcp/server.py` exposes only 3 tools: `scholar_search`, `scholar_inspect` and `scholar_research`. There is no `query_duckdb`, `export_parquet` or `verify_claim_evidence`. `duckdb_hf.py` runs parameterized `httpfs` reads against remote HF Parquet. I found no persisted BM25 store. **P0 is making the README and the tool list agree.**
- **P0: label the Jev fallback clearly.** `jev/client.py` falls back to keyword-affinity "simulation" when there's no key or the call fails, and tags it only as `model_version="jev-simulated-*"`. An agent will treat that as a real semantic judgment. Return `source: live|heuristic` on every predicate result. Heuristic results should be capped at "weak" confidence or blocked from verification verdicts altogether.
- **P0: a retrieval eval harness.** Build 50â€“100 queries with known relevant papers, then measure recall@10 and p95 latency. Without it, "BM25 vs vector" is just opinion.
- **Storage:** a local DuckDB file with the FTS extension plus zone-map range filters will handle a few million rows comfortably for filtered queries. Add DuckDB-VSS only if the eval shows BM25 recall failing on paraphrased or semantic queries. Stay in DuckDB rather than adding LanceDB, so there is one engine. Partition Parquet by `source/year` only. Finer partitions become a small-file problem.
- **No raw SQL for agents.** Expose typed, filtered tools (`year_range`, `min_citations`, `mesh`, `source`). If you really need an escape hatch, run it on a read-only connection with `enable_external_access=false`, a whitelist of views, and forced LIMIT and timeout. Raw `httpfs` plus agent-written SQL lets the agent make arbitrary network requests (SSRF).
- **Context budget:** search returns IDs, titles and 1-line TLDRs by default, with cursor pagination. `scholar_inspect` fetches abstracts one at a time. Citation graphs come back as counts plus the top-k neighbors, never the whole graph.
- **Conflicting claims:** use deterministic evidence tiers (retracted â†’ exclude, preprint < peer-reviewed < meta-analysis/RCT) combined with the predicate probability. Output a structured conflict record, not a merged verdict. Weighting is policy, so it belongs in code, not in an LLM.

**Assumptions & Trade-offs:**
- I'm assuming a single-user or agent-local deployment, not a hosted multi-tenant one.
- Typed tools give up some flexibility in exchange for safety and schema stability.
- Deferring embeddings costs semantic recall on paraphrased queries.

**Risks & Failure Modes:**
- **Jev latency:** earlier measurements from this machine showed about 0.9â€“1.2 s per call (MemoryMaster notes). Per-paper predicate fan-out would take `scholar_research` into minutes. Batch the calls, cache by `(claim_hash, predicate, model_version)`, and cap fan-out per call.
- **Simulated verdicts polluting results:** heuristic output ends up in agent reports as if it were fact.
- **Upstream quotas:** OpenAlex and PubMed rate limits and schema drift break fetchers silently. They need contract tests on recorded fixtures.
- **HF httpfs:** cold reads over the network will blow any sub-50 ms target.

**Reject as premature:** a local ONNX/distilled SLM, LanceDB, citation-graph streaming, and multi-tier Parquet lakes. None has a measured need yet.

**What Would Change My Mind:**
- Eval data showing BM25 recall@10 below about 0.6 on semantic queries would justify VSS.
- An offline or air-gapped user requirement, or Jev pricing or latency making batch verification infeasible, would justify a local distilled model.

**Confidence:** 80%
