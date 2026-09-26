# Round 3 - Gemini

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
