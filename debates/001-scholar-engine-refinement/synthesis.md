# Debate Synthesis: Scholar Engine & MCP: Architecture Refinement, Query Optimization, and Autonomous Verification Roadmap

## Advisor Summary Table

| Advisor | Final Position | Confidence | Key Contribution |
|---|---|---|---|
| **Claude R3** | **Pragmatic Realist** | 85% | Span-level verification (exact character offsets), CI-integrated evaluation harness (50 queries, recall@k, nDCG), and strict result state tracking. |
| **Codex R3** | **Systems Architect** | 89% | Three-stage pipeline architecture (Retrieval, Extraction, Assessment), strict provider-response validation, and query service parameterization. |
| **Gemini R3** | **Contextual Integrator** | 95% | Context-aware evidence hierarchy (moving away from rigid tiers to metadata-driven facets) and robust agent tool safety boundaries. |

---

## Consensus (Unanimously Agreed)

The advisors have converged on a unified set of architectural principles to guide the immediate development of the Scholar Engine:

- **Storage & Analytics Foundation:** DuckDB remains the sole storage and analytical database. Introducing a secondary engine (such as a dedicated vector database or graph database) is deferred until clear performance or recall gaps demand it.
- **Agent Interaction Model:** Agents will never be exposed to raw SQL or free-form query tools due to injection risks, stability issues, and auditability challenges. All database interactions must be mediated by bounded, typed Model Context Protocol (MCP) tools.
- **Architectural Reconciliation:** The immediate priority is aligning the codebase with documented architecture. The current implementation of `scholar_research`—which makes generic relevance claims based on the first 500 characters of truncated abstracts—is rejected as insufficient and must be replaced with true verification.
- **Heuristic vs. Verified Demarcation:** Heuristic outputs and fallback scores must never pass as verified evidence. Every response must carry explicit metadata indicating its generation method, ensuring transparency across the MCP layer.
- **No Silent Failures:** Bad or malformed LLM provider responses must fail visibly and raise alerts rather than defaulting to arbitrary neutral scores (e.g., `0.5`).
- **Data Partitioning:** Database partitioning will be restricted to publication year only. Multi-level partitioning (e.g., year × field × source) is rejected as premature over-engineering.
- **Context Management:** Pagination and selective inspection tools (`inspect_paper`, `inspect_claim`) will be prioritized over complex graph streaming to manage agent context windows.
- **Retraction Handling:** Retracted papers will not be silently deleted or filtered out of the database. They must remain visible to preserve an audit trail, but they must be explicitly excluded from serving as supporting evidence.

---

## Key Disputed Issues & Resolutions

```
                                  [ USER / AGENT QUERY ]
                                            │
                                            ▼
                                  ┌───────────────────┐
                                  │  DuckDB Storage   │
                                  └─────────┬─────────┘
                                            │
                      Step 1: Retrieval     │ (Parameterized SQL)
                                            ▼
                                  ┌───────────────────┐
                                  │  Ranked Papers    │
                                  └─────────┬─────────┘
                                            │
                      Step 2: Extraction    │ (Targeted Passages)
                                            ▼
                                  ┌───────────────────┐
                                  │ Relevant Spans    │
                                  │ & Metadata Facets │
                                  └─────────┬─────────┘
                                            │
                      Step 3: Assessment    │ (LLM / NLI Verification)
                                            ▼
                                  ┌───────────────────┐
                                  │  Verified Claim   │
                                  │  (with Provenance)│
                                  └───────────────────┘
```

| Issue | Claude View | Codex View | Gemini View | Final Resolution |
|---|---|---|---|---|
| **Evidence Hierarchy & Quality** | Drop universal hierarchies. Show study design, population, and directness as metadata facets; let the agent/user weigh them. | Assess via claim-specific relevance, method quality, directness, and publication status. No universal multipliers. | Context-aware hierarchy based on relevance, methodology, and directness, rejecting universal tiers. | **Resolved:** Drop all rigid, universal evidence-tier multipliers (e.g., automatically multiplying scores because a study is an RCT). Expose study design, population size, directness, and publication status as explicit metadata facets, allowing the downstream agent or user to weigh them dynamically. |
| **Verification Granularity** | Span-level verification linking claims to exact sentences/passages with character offsets and source fields. | Three explicit stages: Retrieval (ranked papers), Evidence Extraction (passages with context), and Claim Assessment. | Auditable verification layer validating claims against full abstracts and diverse evidence types. | **Resolved:** Adopt Codex’s 3-stage pipeline (Retrieval $\rightarrow$ Evidence Extraction $\rightarrow$ Claim Assessment) combined with Claude's span-level precision. The Assessment stage will output exactly one of `supports`, `contradicts`, `insufficient_evidence`, or `not_assessed`, accompanied by exact supporting/contradicting spans (character offsets, source field, and document ID). |
| **Evaluation Harness Design** | 50-query versioned eval set with graded relevance and claim-to-span labels, starting with model-drafted/human-corrected labels, running in CI. | Small adjudicated benchmark with held-out subset, testing support, contradiction, insufficient evidence, and malicious text. | Basic retrieval eval harness to measure accuracy and guide future development. | **Resolved:** Build a 50-query versioned evaluation harness run in CI. The benchmark will include synthetic/adversarial cases (contradictions, malicious text, insufficient evidence) and use metrics like recall@k, nDCG, and span-level precision/recall. Labels will start as model-drafted, human-adjudicated, and transition to expert labels. |

---

## Risks & Failure Modes

| Risk | Identified By | Severity | Mitigation Strategy |
|---|---|---|---|
| **Evaluation Set Insufficiency / Overfitting** | Claude | High | Start with 50 diverse queries, but scale to expert-labeled held-out sets. Run automatically in CI as a regression gate to catch model drift early. |
| **Prompt Injection / Instruction Leakage via Source Text** | Codex | Critical | Enforce strict parameter binding, output size caps, timeouts, and complete isolation of source-text inputs within the MCP tool execution boundary. |
| **Silent Failures & Heuristic Masking** | Claude / Gemini | High | Require every response to carry an explicit state (`verified`, `heuristic`, or `failed`). Throw visible errors for malformed LLM provider outputs rather than defaulting to 0.5 or passing off heuristic scores as verified evidence. |
| **Context Window Exhaustion during Deep Inspection** | Claude / Codex | Medium | Implement cursor pagination and specific `inspect_paper` / `inspect_claim` tools to bound the context window size for downstream agents. |

---

## Actionable Engineering Roadmap

### Phase 1: Immediate Critical Path (P0)

1. **Align Implementation with Docs:** Refactor `scholar_research` to verify claims against full abstracts and available text, replacing the 500-character truncation logic.
2. **Three-Stage Verification Contract:** Implement the `Retrieval -> Extraction -> Assessment` pipeline. Enforce span-level verification (capturing document ID, character offsets, source field) and strict result states (`verified`, `heuristic`, `failed`).
3. **Strict Provider Response Validation:** Reject bad or malformed LLM provider outputs; fail visibly instead of defaulting.
4. **CI Eval Harness:** Build the 50-query evaluation suite in CI. Measure recall@k, nDCG, and span precision/recall. Include adversarial test cases (contradictions, malicious inputs).
5. **Typed MCP Tool Boundaries:** Establish parameter binding, timeouts, and output size caps on MCP tools.

### Phase 2: Scalability & Engine Optimization (P1)

1. **Cursor Pagination & Inspection Tools:** Implement cursor-based pagination and introduce `inspect_paper` / `inspect_claim` tools to allow agents to selectively fetch data in bounded chunks.
2. **Metadata-Based Evidence Facets:** Implement ingestion and extraction of study design, population size, directness, and publication status metadata (no universal multipliers).
3. **Retraction Watch Integration:** Ingest Crossref / Retraction Watch data. Expose retraction status as an auditable metadata field and exclude retracted papers from active support claims by default.
4. **Year Partitioning:** Partition the DuckDB storage layer by publication year. Implement query timing and execution plan logging in the eval report.

### Phase 3: Advanced Intelligence & Autonomy (P2)

1. **Hybrid BM25 + Vector Search:** Trial vector embeddings and hybrid search *only* if the Phase 1 eval harness demonstrates a semantic recall gap that justifies the operational complexity.
2. **Local NLI/Entailment Verification:** Implement a local model (e.g., DeBERTa-v3) for verification *only* if API-based verifier cost or latency exceeds the defined budget.

---

## Non-Goals & Discarded Ideas

The following proposals have been explicitly rejected:

- **Raw SQL or Free-form Query Tool:** Rejected as an injection/stability risk and auditability nightmare.
- **Universal Evidence-Tier Multipliers:** Rejected because a rigid hierarchy (e.g., RCT > observational) introduces false precision and fails to account for claim-specific relevance.
- **Graph Databases or Graph Streaming:** Rejected as premature; cursor pagination and selective inspection solve context limitations without the operational overhead of a graph database.
- **Multi-level Partitioning (year × field × source):** Rejected as over-engineering; the current data scale only warrants year partitioning.
- **Silently Filtering Retractions:** Rejected to preserve a complete audit trail.
- **Autonomous Verification without Human-Checked Eval:** Rejected to prevent unchecked model drift.
- **Premature Embedding Model Selection:** Deferred until the evaluation set is active and a semantic recall gap is proven.

---

## Verification & Next Steps

To transition from this synthesis to active development, the engineering team will execute the following immediate steps:

1. **Audit:** Scan the current codebase to identify all instances of 500-character truncation and generic relevance claims.
2. **Schema Definition:** Draft the JSON schema for the 3-stage verification contract and MCP tools, ensuring fields for `document_id`, `character_offsets`, `source_field`, and verification `state` are strictly typed.
3. **Seed Evaluation:** Create the initial 50-query evaluation dataset, including 10 synthetic/adversarial cases, and commit it to version control.
4. **CI Configuration:** Configure the CI pipeline to run the evaluation harness on every pull request, outputting a performance report containing recall@k, nDCG, and span-level precision.