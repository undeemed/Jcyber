# Operator runbook

Jcyber runs only against **in-scope targets** (see the
[legal note](FAQ.md#legal-note)). The scope gate is enforced in code as a
pre-hook on every MCP tool call.

## Prerequisites

- Docker, `uv`, Python 3.12+.
- HexStrike server (clone and run, default `:8899`).
- Caido on `:8889` (proxy) and `:8080` (API). Secrets in `.env`.

## Bring-up

1. **Session brain.** Start Memgraph + Lab:

```
docker compose -f deploy/docker-compose.memgraph.yml up -d
```

Memgraph: `bolt://127.0.0.1:7687`, Lab: `http://127.0.0.1:3000`.

2. **HexStrike.** Start the HexStrike server:

```
cd /path/to/hexstrike && python hexstrike_server.py
```

Default: `http://127.0.0.1:8899`.

3. **Caido.** Start Caido with the proxy pinned:

```
caido-cli --listen 127.0.0.1:8889
```

4. **Install Jcyber:**

```
cd /path/to/Jcyber && uv sync
```

## Starting the MCP server

### Option A: standalone server

```
python -m jcyber serve
```

Starts the MCP server on stdio. Connect your agent harness to it.

### Option B: intake + serve

```
python -m jcyber run https://example.com
```

Creates the engagement directory, writes `scope.toon` and `engagement.toon`,
then starts the MCP server with the engagement pre-loaded.

### Option C: intake only (no server)

```
python -m jcyber intake https://example.com
```

Creates `engagements/<slug>/` with config files. Start the server separately.

## Connecting an agent

Add Jcyber as an MCP server in your agent config:

```json
{
  "jcyber": {
    "type": "stdio",
    "command": "python",
    "args": ["-m", "jcyber", "serve"]
  }
}
```

The agent loads `jcyber/SKILL.md` for methodology and drives the engagement
through MCP tool calls.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HEXSTRIKE_URL` | `http://127.0.0.1:8899` | HexStrike REST endpoint |
| `MEMGRAPH_URI` | `bolt://127.0.0.1:7687` | Memgraph Bolt endpoint |
| `JCYBER_MEMORY_URL` | (none) | TencentDB memory-core endpoint |
| `JCYBER_ENGAGEMENTS` | `./engagements` | Base dir for engagement data |
| `CAIDO_PROXY` | `127.0.0.1:8889` | Caido proxy listener (TCP health-checked) |
| `CAIDO_API_URL` | `http://127.0.0.1:8080` | Caido instance GraphQL API |
| `CAIDO_API_TOKEN` | (none) | Caido access token (Bearer) for instance API |
| `TYPESAFE_API_KEY` | (none) | TypeSafe API key for Jev classifiers |

All secrets can live in `.env` (auto-loaded by `python-dotenv` at startup).

## Ports

| Service | Port | Notes |
|---------|------|-------|
| HexStrike | 8899 | REST API, security tools |
| Caido | 8889 | HTTP proxy, passive plugins |
| Memgraph | 7687 | Bolt protocol |
| Memgraph Lab | 3000 | Web UI |

## Inspecting an engagement

```
python -m jcyber report engagements/example-com    # findings report
python -m jcyber trace engagements/example-com      # decision audit
```

## Bare-link intake

A bare link resolves to: full scan of the target (apex host + all subdomains),
5 rps rate limit, critical-only report focus. A leading `www.` is stripped so
the apex domain is in scope. Non-standard ports are preserved.
