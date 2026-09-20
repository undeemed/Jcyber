# Agent conventions - Jcyber

Repo: an **MCP toolkit** for agent-driven pentesting. The agent harness
(Claude Code, or any MCP-capable LLM) is the reasoning loop. Jcyber provides
scope-gated scanning tools, an evidence graph, a finding lifecycle, and
long-term memory through an MCP server.

## Load-bearing invariants (do not violate when editing this repo)

1. **TOON everywhere machine-written config/state lives.** Every `.toon` file
   is encoder output - produced by `@toon-format/cli` from JSON, never
   hand-formatted. Validate any changed file: `npx -y @toon-format/cli <file>`.

2. **Scope gate is deterministic and code-enforced.** The scope gate in
   `jcyber/mcp_server.py` runs as a pre-hook on every MCP tool call.
   String matching against `scope.toon`, no model, non-bypassable.
   Out-of-scope always wins. A spec edit that gives the scope gate a way
   to be bypassed is wrong.

3. **Exploit tools always require operator confirmation.** The `EXPLOIT_TOOLS`
   set in `mcp_server.py` returns a confirmation prompt instead of executing.
   No exploit tool may auto-execute.

4. **No free-form command construction.** HexStrike calls are (tool-name,
   closed-set params) - target from scope, surface from the graph, sets from
   config. Agent text never reaches a shell, a command string, a path, or a URL.

5. **TencentDB is read at recall, written at commit** (one two-method seam,
   `schema/tencentdb/memory-interface.md`). Nothing touches it mid-run.

6. **HexStrike is the hands only.** Never invoke its `/api/intelligence/*`
   or `bugbounty_*`/`ai_*` MCP tools. Its v6 "Intelligent Decision Engine"
   is source-verified hard-coded heuristics (no model). The agent harness is
   our reasoning layer.

7. **Finding lifecycle is strict.** Evidence -> Hypothesis -> Finding ->
   Validated Finding. No skipping. IDs (H-###, E-###, F-###, VF-###, AC-###)
   are sequential per engagement, never reused.

## Repo layout (what goes where)

| Path | What | Rule |
|------|------|------|
| `PLAN.md` | Architecture and phases | Architecture truth |
| `README.md` | Orientation + quick start | Keep in sync with actual CLI |
| `jcyber/mcp_server.py` | MCP server with all 52 tools | Primary interface |
| `jcyber/SKILL.md` | Agent methodology (pentesting ladder) | Loaded by agent at engagement start |
| `jcyber/scope.py` | Deterministic scope gate | Used as pre-hook by MCP server |
| `jcyber/config.py` | Engagement + scope config parsing | Parses TOON config files |
| `jcyber/clients/` | Adapters for HexStrike, Memgraph, TencentDB, Caido | One adapter per external system |
| `schema/storage-layout.md` | On-disk engagement layout, TOON shapes | Canonical config reference |
| `schema/memgraph/engagement-graph.cypher` | Node/label + index DDL | Cypher must match Memgraph docs |
| `schema/tencentdb/memory-interface.md` | 2-method seam | The only contract with the long-term brain |
| `deploy/docker-compose.memgraph.yml` | Session brain (Memgraph :7687 + Lab :3000) | Schema applied per engagement |
| `examples/idor-walkthrough.md` | One finding traced through MCP tool calls | Must stay consistent with code |
| `engagements/` | Live engagement state | gitignored - never committed |
| `tests/` | pytest suite | Deterministic, no external deps needed |

## Example engagement identity (stay consistent)

The walkthrough uses, and any new example must reuse: slug `acme-lab`,
target `acme-lab.example`, IDs `H-###` / `E-###` / `F-###` / `VF-###` /
`AC-###` (sequential per engagement, never reused), raw files
`evidence/raw/<sha256>.<ext>`.

## Docs discipline

- Every claim about an external system (Memgraph, HexStrike, TencentDB)
  must match its current docs/source - re-fetch before correcting.
- Keep the component roles from `PLAN.md` section 2 - a component doing a job
  another component owns is a plan regression.
