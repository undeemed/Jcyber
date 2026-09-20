# Jcyber - agent conventions (Claude)

See **`AGENTS.md`** for the canonical conventions (this file mirrors it; keep
them in sync). Quick hits:

- This repo is an **MCP toolkit** for agent-driven pentesting: the agent
  harness (Claude Code, or any MCP-capable LLM) is the reasoning loop.
  Jcyber provides scope-gated scanning tools, an evidence graph, a finding
  lifecycle, and long-term memory via an MCP server.
- **TOON** for all machine-written config/state (`.toon` = `@toon-format/cli`
  encoder output from JSON; validate with `npx -y @toon-format/cli`).
  Canonical encodings: `schema/storage-layout.md`.
- **Scope gate = deterministic string matching**, enforced as a code pre-hook
  on every MCP tool call in `jcyber/mcp_server.py`. Not prompt-bypassable.
  Out-of-scope always wins.
- **Exploit tools require operator confirmation** - the `EXPLOIT_TOOLS` set
  in `mcp_server.py` returns a confirmation prompt instead of executing.
- **No free-form command construction:** HexStrike = (tool, closed-set
  params); agent text never reaches a shell/path/URL.
- **TencentDB:** recall at intake, commit at close; never in the hot path;
  backend is swappable (`schema/tencentdb/memory-interface.md`).
- **HexStrike:** hands only - never its `bugbounty_*`/`ai_*`/
  `/api/intelligence/*` (its v6 "engine" = hard-coded heuristics, no model).
- **Finding lifecycle:** Evidence (E-###) -> Hypothesis (H-###) -> Finding
  (F-###) -> Validated Finding. No skipping. IDs sequential, never reused.
- `engagements/` gitignored (never committed); `docs/` =
  `diagrams.md` (Mermaid stack + tool-call flow) + `FAQ.md` (FAQ,
  comparison, legal note) + `RUNBOOK.md` (operator bring-up).
- Runtime: `jcyber/mcp_server.py` = MCP server (52 tools); `jcyber/SKILL.md`
  = agent methodology; adapters in `jcyber/clients/`; `jcyber/intake.py` =
  bare-link intake. `tests/` = pytest; `scripts/check_docs.sh` +
  `.github/workflows/ci.yml` enforce invariants.
- Docs discipline: external-system claims (Memgraph/HexStrike/TencentDB)
  match current docs/source; re-fetch before correcting.
