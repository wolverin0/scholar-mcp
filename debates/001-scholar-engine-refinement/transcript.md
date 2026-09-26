# Full Transcript: Scholar Engine & MCP: Architecture Refinement, Query Optimization, and Autonomous Verification Roadmap

**Debate ID:** `001-scholar-engine-refinement`  
**Participants:** Claude (Anthropic), Codex (OpenAI), Gemini (Google)  
**Date:** 2026-09-26 20:47:48Z  

---

## Round 1: Independent Technical Positions

### Claude (Round 1)
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

---

### Codex (Round 1)
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

---

### Gemini (Round 1)
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

---

## Round 2: Cross-Examination & Stress-Testing

### Claude (Round 2)
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

---

### Codex (Round 2)
**Agreements:** Both correctly prioritize measured retrieval quality, bounded typed tools, explicit provenance, and deferring additional engines until justified. Claude’s distinction between implemented capabilities and roadmap claims is essential. Heuristic fallback must never silently become evidence verification. Pagination and selective inspection should precede graph streaming.

**Critique of Claude:** The proposed evidence hierarchy is too universal. An RCT, meta-analysis, or peer-reviewed paper is not automatically stronger evidence for every claim; study relevance, methodology, population, and directness matter. Retractions should remain visible with their status for auditability, even when excluded from supporting evidence. Multiplying evidence tiers by predicate probabilities would imply calibration that has not been demonstrated.

“DuckDB handles millions comfortably” needs a workload and hardware qualification. Measure index construction, refresh behavior, memory, concurrency, and filtered retrieval—not just query latency. Likewise, 50–100 queries provide a useful smoke benchmark, but weak grounds for a universal recall threshold. Stratify by corpus, terminology, paraphrase, and filter selectivity.

The proposed cache key omits evidence identity and revision. Identical claims evaluated against different passages must not share verdicts. Historical latency from another project is a hypothesis, not a Scholar measurement.

**Critique of Gemini:** Semantic recall and latency are different acceptance criteria. BM25 cannot become semantically adequate merely by meeting 50 ms; vectors might improve recall while increasing latency. Neither architecture should be selected from that latency target alone.

Venue prestige and recency are poor conflict-resolution rules. Newer papers can be weaker, and venue does not establish claim-level support. Preserve disagreement instead of automatically choosing a winner.

Your endpoint names also differ from Claude’s reported inventory. Reconcile the actual interface before prioritizing optimization or introducing `safe_query`. Typed search filters may already cover the required use cases. Partitioning needs evidence about file sizes and access patterns; define whether `source_id` means a few corpora or many publishers.

**Defended / Refined Position:** Establish three separate gates: retrieval relevance, evidence entailment, and operational reliability. First reconcile contracts and eliminate ambiguous fallback. Then benchmark the existing pipeline with cold/warm latency, recall, payload size, cost, and failure rates.

Verification should return evidence passages, provenance, model/policy versions, and explicit support, contradiction, or insufficient-evidence outcomes. Cache against claim, evidence revision, predicate, and evaluator configuration.

Autonomous acceptance must include adversarial tests: irrelevant high-prestige papers, contradictory passages, upstream outages, stale caches, and heuristic fallback. Treat retrieved text as untrusted input. Add hybrid retrieval or local inference only when a measured failure or explicit offline requirement warrants it.

**Confidence:** 89%

---

### Gemini (Round 2)
**Agreements:**
Both Claude and Codex correctly identify the critical P0 of **reconciling the documented architecture with the current implementation**. This foundational step is non-negotiable for building a reliable roadmap. I strongly agree that **DuckDB is the appropriate analytical foundation** for initial development, and that **vector embeddings should be deferred** until a measurable recall gap on semantic queries is demonstrated. The emphasis on **auditable verification, structured evidence, and clear demarcation of heuristic vs. actual results** is also a key shared strength. Both also rightly prioritize **typed tools for agent interaction** over raw SQL, citing security and stability concerns.

**Critique of Claude:**
Claude's proposal for a **retrieval eval harness** is excellent, but 50-100 queries might be insufficient for robustly evaluating recall@10 across diverse query types and edge cases. The "P0 is making the README and the tool list agree" is crucial, but it's a documentation/consistency P0, not strictly an *architecture refinement* P0. While correct that "weighting is policy," Claude's strict "deterministic evidence tiers" might be overly rigid, potentially hindering nuanced conflict resolution where LLMs could provide valuable contextual assessment (though not final policy) before code-based adjudication.

**Critique of Codex:**
Codex's call for **"expert-labeled claim/evidence pairs"** for release gates is ideal but represents a substantial, expensive data generation effort that might slow initial progress. While comprehensive, the proposed **"million-paper workloads" benchmarking** might be over-engineered for an initial single-node deployment, potentially diverting resources from core feature development. The security posture for "optional SQL" is laudably thorough, but it approaches a level of restriction that practically negates the utility of an SQL escape hatch for an agent, effectively reinforcing "no raw SQL" by making it almost unusable.

**Defended / Refined Position:**
My position remains focused on **iterative, evidence-driven development**. The absolute P0 is indeed **code-to-docs alignment and establishing a baseline retrieval evaluation harness (with at least 200-300 queries)**. We must implement **auditable, structured verification that clearly flags heuristic results** and prioritizes safety with **typed, bounded tools**. While a full "million-paper" benchmark is premature, **cold-cache performance and concurrent reader tests** on a representative dataset (e.g., 100k-500k papers) are essential before scaling. For conflicting claims, a **structured conflict record** is key, allowing policy (code) to apply deterministic tiers while potentially leveraging LLM capabilities for *identifying and summarizing* nuances in the conflict, not for final adjudication.

**Confidence:** 85%

---

## Round 3: Convergence & Roadmap Proposals

### Claude (Round 3)
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

---

### Codex (Round 3)
**Consensus Items:**  
All three advisors converge on DuckDB as the analytical foundation, bounded typed MCP tools instead of agent-facing SQL, and measurement before adding retrieval engines. The immediate priority is reconciling architectural claims with implemented behavior. Evidence must carry provenance; heuristic relevance must remain visibly distinct from verification. Vector search and local models require demonstrated benefits before adoption.

**Final Architecture Compromise:**  
Separate the system into three explicit stages:

1. **Retrieval:** Return ranked papers with stable identifiers, metadata, retrieval method, and pagination. Ranking scores describe relevance, not claim validity.
2. **Evidence extraction:** Retrieve passages addressing a specific claim, preserving source location, source version, and surrounding context. Abstract-only access must be declared; missing full text limits conclusions.
3. **Claim assessment:** Produce `supports`, `contradicts`, `insufficient_evidence`, or `not_assessed`, with cited passages, rationale, and assessment method. Abstain when evidence or provider output is inadequate.

Keep DuckDB behind a shared query service with parameterized templates, validated filters, bounded result sizes, and execution limits. Use year-only partitioning if external columnar storage warrants partitioning; verify benefits against representative workloads.

Assess evidence through claim-specific relevance, methodological quality, directness, and publication status. Retain retracted records for auditability while excluding them from supporting evidence by default. Avoid a universal evidence-tier multiplier.

**Prioritized Action Items:**

| Priority | Deliverable | Rationale / acceptance |
|---|---|---|
| **P0** | Audit implementation against public contracts; remove unsupported verification claims. | Generic relevance statements and truncated-abstract checks cannot establish claim support. |
| **P0** | Implement the staged evidence contract and strict provider-response validation. | Reject malformed responses; expose heuristic fallback throughout MCP output; test abstention and contradiction handling. |
| **P0** | Establish a small, adjudicated benchmark with a held-out subset. | Include support, contradiction, insufficient evidence, and malicious source text. Synthetic cases test mechanics, not scientific accuracy. |
| **P0** | Enforce typed-tool resource and safety boundaries. | Test parameter binding, pagination, timeouts, output caps, and source-text instruction isolation. |
| **P1** | Optimize retrieval using query plans and benchmark failures. | Measure recall@k, ranking quality, latency, and cost before changing indexing or storage layout. |
| **P1** | Expand human-reviewed evaluation and provenance coverage. | Track unsupported assessments, citation correctness, abstention behavior, and retraction handling independently. |
| **P2** | Trial hybrid/vector retrieval or local assessment models. | Adopt only after reproducible gains justify operational cost and complexity. |

**Rejected Ideas / Non-Goals:**  
No raw SQL for agents, graph streaming before bounded inspection proves insufficient, universal evidence rankings, arbitrary probability multiplication, or fabricated default confidence. No additional database, vector infrastructure, or autonomous “scientific truth” claims without evaluation evidence.

**Final Confidence:** 89%

---

### Gemini (Round 3)
**Consensus Items:**
All three models converge on several critical architectural principles. DuckDB is the agreed-upon analytical foundation, with vector search and local models correctly deferred until measurable recall gaps are demonstrated. Raw SQL interaction for agents is rejected in favor of bounded, typed tools. The paramount P0 is reconciling the documented architecture with the current implementation, making auditable verification the immediate focus. Finally, all agree on clear demarcation of heuristic vs. actual results and explicit provenance.

**Final Architecture Compromise:**
The Scholar Engine will initially leverage DuckDB for structured data storage and analytical querying, with agent interactions strictly mediated by typed tools for security and stability. The core architectural focus is a robust, auditable verification layer that explicitly validates claims against evidence, distinguishing clearly between derived facts and heuristic fallbacks. This layer is paramount for establishing trust and reliability, forming the foundation before any advanced retrieval or generative capabilities are considered. Provenance for all claims will be explicit.

**Prioritized Action Items:**
**P0 (Immediate & Foundational):**
*   **Reconcile Architecture & Implementation:** Implement the `scholar_research` verification against full abstracts and diverse evidence types, moving beyond generic relevance claims. This is the shared P0.
*   **Robust Provider Response Handling:** Implement explicit rejection of invalid or bad provider responses, preventing silent defaults.
*   **Clear Heuristic Marking:** Ensure all heuristic scores and fallback mechanisms are clearly marked as such throughout the MCP response for auditability.
*   **Basic Retrieval Eval Harness:** Develop a system to measure retrieval quality and verification accuracy to guide future development.

**P1 (High Priority - Next Steps):**
*   **Refined Evidence Hierarchy:** Develop a structured, context-aware evidence hierarchy that considers study relevance, methodology, and directness, rather than universal tiers.
*   **Expanded Typed Tools:** Enhance the range and robustness of typed tools for agent interaction, enabling more complex yet controlled operations.
*   **Partitioning by Year:** Implement data partitioning within DuckDB exclusively by publication year for optimized querying.

**P2 (Future Roadmap):**
*   **Pagination & Selective Inspection:** Explore efficient ways to handle large result sets without immediate reliance on complex streaming architectures.

**Rejected Ideas / Non-Goals:**
*   **Premature Vector Embeddings/Local Models:** Deferring these until a demonstrated need (e.g., semantic recall gap) prevents over-engineering and resource waste.
*   **Silent Defaulting of Bad Responses:** This undermines reliability and auditability.
*   **Graph Streaming for Retrieval:** Overly complex for initial needs; simpler pagination and selective inspection are preferred.
*   **Overly Universal Evidence Tiers:** Evidence strength must be contextualized by claim, methodology, and relevance, not a rigid, universal hierarchy.
*   **Multiplying Evidence Tiers by Predicate Probabilities:** An unnecessary layer of complexity for current verification goals.

**Final Confidence:**
95%
