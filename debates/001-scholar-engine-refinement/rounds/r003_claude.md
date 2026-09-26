# Round 3 - Claude

**Consensus Items:**
- DuckDB stays the only storage and analytics layer. No second engine is justified yet.
- The top priority is making the code match the documented architecture. Today `scholar_research` emits generic relevance claims checked against only the first 500 characters of each abstract. That is not verification.
- Agents use bounded, typed tools and never get raw SQL.
- Vector embeddings and a local model are deferred until a measured recall gap justifies them.
- Heuristic output must never pass as verified evidence.
- Pagination and selective inspection come before graph streaming.
- Partition by year only.

**Final Architecture Compromise:**
One DuckDB store feeds a typed MCP layer with three kinds of tools: search, inspect and verify.

- **Verification** becomes span-level. Each claim links to the exact supporting sentence or passage, with document ID, character offsets and source field. Claims made without a span are labeled `unsupported`, not scored.
- **Result states:** every result carries exactly one of `verified`, `heuristic` or `failed`. Bad provider responses fail visibly and never default to 0.5.
- **Evidence quality:** I concede Codex's critique. I'm dropping the universal evidence hierarchy (meta-analysis > RCT > peer-reviewed paper). Instead, study design, population and directness are shown as metadata facets, and the agent or user weighs them per claim.
- **Retractions** stay visible with their status for auditability. They are excluded from supporting evidence only.
- **Quality measurement** uses a small, versioned eval set: about 50 queries, with graded relevance and claim-to-span labels. It starts with labels the model drafts and a human then corrects, and grows toward labels written by experts.

**Prioritized Action Items:**

| Pri | Item | Rationale |
|---|---|---|
| **P0** | Span-level verification over full abstracts or full text, replacing the 500-character truncation | The core promise is currently false |
| **P0** | The `verified` / `heuristic` / `failed` state carried through to the MCP response; reject bad provider responses | Stops heuristic scores being passed off as evidence |
| **P0** | Eval harness: 50 labeled queries, recall@k, nDCG and span precision, run in CI as a regression gate | Every later decision needs a number |
| **P0** | Documentation matches the implementation, with capabilities not yet built marked as roadmap | Removes the gap between the docs and the code |
| **P1** | Cursor pagination plus `inspect_paper` / `inspect_claim` tools | Bounded context for agents |
| **P1** | Retraction ingestion (Crossref / Retraction Watch) exposed as a status field | Auditability |
| **P1** | Year partitioning and query timing in the eval report | Fix performance only when it is measured |
| **P2** | Hybrid BM25 + vector search, only if the harness shows a semantic recall gap above a set threshold | Earned by data, not assumed |
| **P2** | Local NLI or entailment model for verification, if the API-based verifier's cost or latency fails a budget | Same rule: build it only when a measured threshold is crossed |

**Rejected Ideas / Non-Goals:**
- **Raw SQL or a free-form query tool for agents:** an injection and stability risk, and it can't be audited.
- **A universal evidence-tier multiplier on top of predicate probabilities:** false precision, and it makes the reasoning wrong for many claims.
- **Graph streaming or a graph database now:** no measured need, and pagination solves the context problem.
- **Multi-level partitioning (year × field × source):** the scale is too small, and it makes files and maintenance more complex.
- **Silently filtering out retractions:** it destroys the audit trail.
- **Autonomous verification running without human-checked eval labels:** there's no way to catch the verifier drifting.
- **Choosing an embedding model up front:** premature before the eval set exists.

**Final Confidence:** 85%. The P0 set is well supported. The remaining risk is whether 50 labels are enough to detect the recall gap that would unlock P2.
