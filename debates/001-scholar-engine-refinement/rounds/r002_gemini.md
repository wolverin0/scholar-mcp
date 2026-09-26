# Round 2 - Gemini

**Agreements:**
Both Claude and Codex correctly identify the critical P0 of **reconciling the documented architecture with the current implementation**. This foundational step is non-negotiable for building a reliable roadmap. I strongly agree that **DuckDB is the appropriate analytical foundation** for initial development, and that **vector embeddings should be deferred** until a measurable recall gap on semantic queries is demonstrated. The emphasis on **auditable verification, structured evidence, and clear demarcation of heuristic vs. actual results** is also a key shared strength. Both also rightly prioritize **typed tools for agent interaction** over raw SQL, citing security and stability concerns.

**Critique of Claude:**
Claude's proposal for a **retrieval eval harness** is excellent, but 50-100 queries might be insufficient for robustly evaluating recall@10 across diverse query types and edge cases. The "P0 is making the README and the tool list agree" is crucial, but it's a documentation/consistency P0, not strictly an *architecture refinement* P0. While correct that "weighting is policy," Claude's strict "deterministic evidence tiers" might be overly rigid, potentially hindering nuanced conflict resolution where LLMs could provide valuable contextual assessment (though not final policy) before code-based adjudication.

**Critique of Codex:**
Codex's call for **"expert-labeled claim/evidence pairs"** for release gates is ideal but represents a substantial, expensive data generation effort that might slow initial progress. While comprehensive, the proposed **"million-paper workloads" benchmarking** might be over-engineered for an initial single-node deployment, potentially diverting resources from core feature development. The security posture for "optional SQL" is laudably thorough, but it approaches a level of restriction that practically negates the utility of an SQL escape hatch for an agent, effectively reinforcing "no raw SQL" by making it almost unusable.

**Defended / Refined Position:**
My position remains focused on **iterative, evidence-driven development**. The absolute P0 is indeed **code-to-docs alignment and establishing a baseline retrieval evaluation harness (with at least 200-300 queries)**. We must implement **auditable, structured verification that clearly flags heuristic results** and prioritizes safety with **typed, bounded tools**. While a full "million-paper" benchmark is premature, **cold-cache performance and concurrent reader tests** on a representative dataset (e.g., 100k-500k papers) are essential before scaling. For conflicting claims, a **structured conflict record** is key, allowing policy (code) to apply deterministic tiers while potentially leveraging LLM capabilities for *identifying and summarizing* nuances in the conflict, not for final adjudication.

**Confidence:** 85%
