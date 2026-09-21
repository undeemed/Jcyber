# Setup Guide

Get Jcyber running in under 5 minutes. By the end you'll have an agent
driving a pentest through 54 MCP tools with scope enforcement.

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Docker (for Memgraph)
- [HexStrike](https://github.com/0x4m4/hexstrike-ai) cloned locally

## Step 1: Install

```
cd Jcyber
uv sync
```

For Jev classifiers (optional, 8.7x faster severity/duplicate checks):
```
uv sync --extra jev
```

## Step 2: Start the backends

**Memgraph** (engagement graph):
```
docker compose -f deploy/docker-compose.memgraph.yml up -d
```

**HexStrike** (scanning tools):
```
cd /path/to/hexstrike-ai
pip install -r requirements.txt
python hexstrike_server.py
```

Verify both are up:
```
curl http://127.0.0.1:8888/health    # HexStrike -> 200
uv run python -m jcyber.clients.memgraph --smoke   # Memgraph -> ok
```

## Step 3: Set up secrets

Create `.env` in the Jcyber directory (gitignored):
```
TYPESAFE_API_KEY=your_key_here
```

Only needed if you installed the `jev` extra. The MCP server works without it.

## Step 4: Add to your agent

**Claude Code / OMP:** Add to `~/.omp/agent/mcp.json`:

```json
{
  "mcpServers": {
    "jcyber": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "/path/to/Jcyber", "python", "-m", "jcyber", "serve"]
    }
  }
}
```

Reload MCP servers (`/mcp reload` in OMP).

**Other MCP clients:** Point your client at `uv run python -m jcyber serve`
over stdio. The server exposes 54 tools.

## Step 5: Start a session

1. Open a new chat in your agent (Claude Code / OMP)
2. Select the **Jcyber** folder as the working directory
3. The agent picks up `SKILL.md` for pentesting methodology
4. Tell the agent your target:

```
Run a pentest against http://127.0.0.1:4280
```

The agent will:
- Call `intake_target` to create the engagement
- Run scanning tools (`httpx_probe`, `nmap_scan`, `nuclei_scan`, ...)
- Create hypotheses from evidence
- Promote confirmed findings
- Score severity
- Render a report when done

All targets are scope-checked before every tool call. Exploit tools require
your confirmation.

## Verify it works

Quick smoke test without a real target:
```
uv run python -m jcyber serve
```

If it prints `[jcyber] HexStrike connected` and `[jcyber] Memgraph connected`,
you're good.

## Ports

| Service | Port | What |
|---------|------|------|
| HexStrike | 8888 | Security tools REST API |
| Memgraph | 7687 | Engagement graph (Bolt) |
| Memgraph Lab | 3000 | Graph web UI |
| Caido | 8889 / 8080 | HTTP proxy (8889) and instance API (8080) |

## Troubleshooting

**MCP server won't start:** Check `uv sync` completed and both backends are
running.

**Tools return `[tool_error]`:** HexStrike is running but the specific tool
binary isn't installed (e.g., nmap, nuclei). Install the tool on the host
machine.

**Jev tools fail:** Set `TYPESAFE_API_KEY` in `.env` or your environment.

**Scope blocks everything:** Check your target matches the engagement scope.
Run `python -m jcyber intake <url>` to see what scope is generated.
