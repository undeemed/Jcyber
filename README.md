# Jcyber

[![CI](https://github.com/undeemed/Jcyber/actions/workflows/ci.yml/badge.svg)](https://github.com/undeemed/Jcyber/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![M8ven Score](https://m8ven.ai/badge/mcp/undeemed-jcyber-1hp3zt)](https://m8ven.ai/mcp/undeemed-jcyber-1hp3zt)

**MCP toolkit for agent-driven pentesting.** The agent harness (Claude Code,
or any MCP-capable LLM) is the reasoning loop. Jcyber provides scope-gated
scanning tools, an evidence graph, a finding lifecycle, and long-term memory
through an MCP server.

## How it works

```
Agent Harness (Claude Code / any MCP client)
    |
    | MCP protocol (stdio)
    v
Jcyber MCP Server ---- scope gate (pre-hook, every call)
    |          |            |             |
    v          v            v             v
HexStrike  Memgraph    TencentDB      Caido
(:8888)    (:7687)     (memory)       (:8889)
    |                                    |
    +----------> Target <----------------+
```

The agent decides what to scan, when to create hypotheses, and when to
promote findings. Jcyber enforces safety in code: the scope gate runs
before every tool call, exploit tools require operator confirmation, and all
evidence is normalized into the engagement graph.

## The systems

| Component | Role |
|-----------|------|
| HexStrike | Hands - 150+ security scanning tools via REST |
| Memgraph | Session brain - engagement graph (evidence, hypotheses, findings) |
| TencentDB | Long-term memory - cross-engagement recall and learning |
| Caido | Traffic substrate - proxy, request logging, passive plugins |

## MCP tools (54 total)

- **42 HexStrike scanning tools** - `nmap_scan`, `nuclei_scan`, `sqlmap_scan`, `ffuf_scan`, `httpx_probe`, etc. Each scope-gated.
- **Graph tools (4)** - `create_hypothesis`, `promote_finding`, `score_finding`, `retire_hypothesis`
- **Engagement tools (4)** - `intake_target`, `get_state`, `render_findings_report`, `get_decision_trace`
- **Memory tools (2)** - `recall_lessons`, `commit_learnings`
- **Jev classifiers (2)** - `suggest_severity`, `check_duplicate`

## Requirements

- **Python 3.12+** and [`uv`](https://docs.astral.sh/uv/)
- **Docker** (for Memgraph)
- **HexStrike server** running on `:8888`
- **Caido** proxy on `:8889` (API on `:8080`)
- **Secrets in `.env`:** `TYPESAFE_API_KEY`, `CAIDO_API_TOKEN` (auto-loaded by `python-dotenv`)

### Ports

| Service | Port | Notes |
|---------|------|-------|
| HexStrike | 8888 | REST API for security tools |
| Caido | 8889 | HTTP proxy, passive plugins |
| Memgraph | 7687 | Bolt protocol (graph DB) |
| Memgraph Lab | 3000 | Web UI for graph inspection |

## Quick start

**1. Install.**

```
uv sync
```

**2. Start the session brain (Memgraph).**

```
docker compose -f deploy/docker-compose.memgraph.yml up -d
```

**3. Start the MCP server.**

Option A - standalone server (connect your agent separately):
```
python -m jcyber serve
```

Option B - intake a target and start serving:
```
python -m jcyber run https://example.com
```

**4. Connect your agent.** Add the MCP server to your agent's config. For
Claude Code / OMP, add to your MCP config:

```json
{
  "jcyber": {
    "type": "stdio",
    "command": "python",
    "args": ["-m", "jcyber", "serve"]
  }
}
```

The agent reads the SKILL.md methodology and drives the engagement through
MCP tool calls.

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HEXSTRIKE_URL` | `http://127.0.0.1:8888` | HexStrike REST endpoint |
| `MEMGRAPH_URI` | `bolt://127.0.0.1:7687` | Memgraph Bolt endpoint |
| `JCYBER_MEMORY_URL` | (none) | TencentDB memory-core endpoint |
| `CAIDO_PROXY` | `127.0.0.1:8889` | Caido proxy listener (TCP health-checked) |
| `CAIDO_API_URL` | `http://127.0.0.1:8080` | Caido instance GraphQL API |
| `CAIDO_API_TOKEN` | (none) | Caido access token (in `.env`) |
| `TYPESAFE_API_KEY` | (none) | TypeSafe API key for Jev classifiers (in `.env`) |
| `JCYBER_NONINTERACTIVE` | (unset) | Set `1` to abort on missing services (no prompt) |

Secrets live in `.env` (auto-loaded by `python-dotenv` at startup).

## Safety

- **Scope gate** - deterministic string matching against the engagement scope, enforced as a pre-hook on every MCP tool call. Not prompt-bypassable.
- **Exploit confirmation** - exploit tools (`metasploit_run`, `hydra_attack`, etc.) return a confirmation prompt instead of executing. Operator must approve.
- **Evidence graph** - all tool output is normalized, sha256-deduped, and stored in Memgraph with full provenance.
- **Finding lifecycle** - Evidence (E-###) -> Hypothesis (H-###) -> Finding (F-###) -> Validated Finding. No skipping.

## CLI

```
python -m jcyber serve              # start MCP server (stdio)
python -m jcyber run <url>          # intake target + start MCP server
python -m jcyber intake <link>      # create engagement directory
python -m jcyber report <dir>       # render engagement report
python -m jcyber trace <dir>        # render decision trace
```

## Layout

```
jcyber/
  mcp_server.py        MCP server with all 54 tools
  SKILL.md             Agent methodology (the pentesting ladder)
  scope.py             Deterministic scope gate
  normalize.py         Evidence normalization (sha256, summary)
  config.py            Engagement + scope config parsing
  intake.py            Bare-link intake (URL -> engagement)
  report.py            Report renderer (graph -> Markdown)
  trace.py             Decision trace renderer
  learn.py             Distiller (findings -> long-term memory)
  ports.py             Protocol interfaces
  types.py             Domain types (Evidence, Scope, Severity)
  clients/
    hexstrike.py       HexStrike REST adapter
    memgraph.py        Memgraph Bolt adapter
    tencentdb.py       TencentDB HTTP adapter
    caido.py           Caido GraphQL adapter
    toon.py            TOON codec (CLI wrapper)
schema/
  memgraph/            Engagement graph DDL + indexes
  storage-layout.md    TOON config shapes
  tencentdb/           Memory interface spec
tests/                 pytest suite (no external deps needed)
deploy/                Docker Compose for Memgraph
```

## Testing

```
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run pyright
```

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Legality

Jcyber assumes **in-scope targets only**. The scope gate is load-bearing,
not decorative: it is deterministic string matching enforced in code as a
pre-hook on every MCP tool call. Out-of-scope targets are rejected before
reaching any scanner. Nothing in this repo grants permission to test any
system. Authorization is the operator's responsibility.

## License

MIT - see `LICENSE`.
