# Round 3 - Codex

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
