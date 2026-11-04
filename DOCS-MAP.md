# DOCS-MAP

One line per document: path — purpose — status (audited 2026-11-04).
Status: **current** = matches the code today; **historical** = frozen record, names things that do not exist in the code; **n/a** = not present.

| Document | Purpose | Status |
| :--- | :--- | :--- |
| `README.md` | Project overview, install, configuration, tests, MCP client setup, tool reference, CLI | current (install/run/test commands verified 2026-11-04) |
| `DOCS-MAP.md` | This index of documentation | current |
| `LICENSE` | MIT license text | current |
| `.env.example` | Template for `TYPESAFE_API_KEY` (placeholder only; not auto-loaded by the code) | current |
| `requirements.txt` | Pip install list used by the README (runtime + pytest) | current (needs `mcp<2` alongside, see README) |
| `pyproject.toml` | Package metadata and console scripts `scholar`, `scholar-mcp` | stale for install: `pip install -e .` fails (flat-layout discovers `scholar` + `debates`) |
| `AGENTS.md` / `CLAUDE.md` | Agent instructions | n/a (not present in the repo) |
| `debates/viewer.html` | Static HTML viewer for debates; loads `index.json`, `state.json`, `transcript.md`, `synthesis.md`, `context.md`, `rounds/*.md` | current (all referenced files exist) |
| `debates/index.json` | List of debate folders for the viewer | current |
| `debates/001-scholar-engine-refinement/context.md` | Brief given to the AI debate participants | historical: describes tools/files not in the code (`search_papers`/`get_paper_details`/`query_duckdb`/`validate_claim_predicate`/`verify_claim_evidence`/`export_parquet` MCP tools, `scholar.duckdb`, Europe PMC/PubMed/bioRxiv/ClinicalTrials sources, Python 3.12+) |
| `debates/001-scholar-engine-refinement/state.json` | Debate run metadata (participants, timings) | historical: `working_dirs` point to the author's local Windows paths |
| `debates/001-scholar-engine-refinement/transcript.md` | Full 3-round debate transcript | historical: proposes `query_duckdb`, `safe_query`, `export_parquet`, `get_paper_details`, `verify_claim_evidence`, `inspect_claim` (not implemented) |
| `debates/001-scholar-engine-refinement/synthesis.md` | Consolidated roadmap from the debate | historical/roadmap: names `inspect_claim` (not implemented) |
| `debates/001-scholar-engine-refinement/rounds/r00{1,2,3}_{claude,codex,gemini}.md` | Individual debate round answers (9 files) | historical: several name unimplemented tools (`query_duckdb`, `safe_query`, `export_parquet`, `get_paper_details`, `verify_claim_evidence`, `inspect_claim`) |
