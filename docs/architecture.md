# Architecture and compatibility

The `src/autoreference` package owns all executable logic. `skills/autoreference` contains host-agent instructions, the JSON protocol, and a launcher bound to the pinned installed runtime. No Codex API, model SDK, or browser is required for basic tasks.

## Responsibilities

- `models` and `matching`: reference identity, provenance, conflict recording. Different DOIs cannot merge; a title-only match is not bibliographic verification.
- `documents`: deterministic, read-only TXT/DOCX/TEX extraction; original citation keys and source positions; unsupported content remains visible in warnings.
- `providers` and `verification`: public retrieval and bibliographic lookup with bounded HTTP retries. AnySearch authentication and parse failures remain distinguishable from empty results.
- `workflow`: typed request validation, stable IDs, exclusive task locks, atomic JSON checkpoints, candidate/evidence/decision state, and conservative artifact export.
- `access`: an owned, dedicated browser profile for human login. It never reads personal browser profiles or asks for passwords. Cached access status is not a live access guarantee.
- `cli`, `agent_cli`, `web`, `llm`: adapters. Existing search, plain-text paper, WebUI and model-API flows remain supported; the agent task adapter does not instantiate an LLM client.

## Task flow

Prepare → host selects claims/queries → search → verify → host reads evidence and judges support → finalize. Each stage writes to the same dedicated task directory. A failed source does not delete another source's candidates. Only changed/explicitly refreshed queries run again. Search checkpoints after each claim; finalization merges decisions across batches.

The report records metadata status independently of support. Evidence may be returned by a provider or supplied by the host after reading a source; the latter is explicitly attributed to the agent. Exact quote checks establish consistency with recorded content, not independent source authenticity or semantic correctness.

Raw existing reference fields can be supplied by the host only when they occur in the original string. DOI lookup requires matching authoritative metadata; no-DOI lookup additionally needs title, author and year agreement. Unresolved raw references remain in the report. Verified existing BibTeX is enriched/corrected using the authoritative record while preserving original keys and nonstandard fields; changes remain in the report. Unverified entries retain their original fields. Historical source differences resolved by authoritative metadata are distinct from unresolved identity conflicts.

Generated BibTeX keys preserve original keys and aliases, while new deterministic keys are checked for collisions. Export refuses unmanaged pre-existing files. Task directories should not be shared between different source documents.

## Access and installation

A campus request that cannot proceed is reported as needing user action. For campus-only requests, failed access triggers public-source fallback. Within a batch, an observed campus barrier is reused rather than repeatedly opening browsers. The skill prompts once per obstacle and permits one search retry after the user finishes the requested action; skipping always preserves public results.

The installer creates versioned virtual environments and switches its launcher configuration only after runtime installation and diagnostics succeed. Update checks file hashes and restores previous files on failure; uninstall preflights ownership and removes only recorded components. Unrelated user files and directories survive. Installation uses an exclusive lock and requires an explicit destination supported by the host agent.

Runtime credentials, profiles, research inputs, generated reports, environments, backups and distribution outputs are excluded from Git. Installing a release does not copy repository private files. Compatible task protocol: `1.0`; incompatible schemas are rejected rather than silently migrated.

## Known boundaries

No PDF/OCR, general TeX macro expansion, compilation, automated citation insertion, arbitrary SSO adapter or MCP server is provided. Complex DOCX citation fields and nonstandard TeX constructs can require host review. Crossref cannot verify every DOI registration agency; unresolved candidates remain unverified. Abstract-only judgments must be qualified to the evidence actually seen. Browser access depends on the institution, network, Chrome and driver; only a successful real query establishes access.
