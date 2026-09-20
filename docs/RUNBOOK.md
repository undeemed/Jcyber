# Operator runbook (P2 — live engagement)

This is the human-supervised path. Jcyber runs only against **in-scope
targets** (see the [legal note](FAQ.md#legal-note)). The loop's
deterministic scope gate is load-bearing, not decorative: the scope the
operator defines in `scope.toon` is the source of truth it enforces.

## Prerequisites

- Docker, Node 20+, `uv`, Python 3.12+.
- Secrets in the operator environment (never written to any file in the repo):
  - `TYPESAFE_API_KEY` — Jev (the control-path model).
  - `CEREBRAS_API_KEY` — BYOK engine, only if `engine.enabled` in `engagement.toon`.
  - `JCYBER_MEMORY_URL` — the TencentDB memory seam endpoint.
- Optional overrides: `MEMGRAPH_URI` (default `bolt://127.0.0.1:7687`),
  `HEXSTRIKE_URL` (default `http://127.0.0.1:8888`).

## Bring-up

1. **Session brain.** Start Memgraph + Lab:
   ```
   docker compose -f deploy/docker-compose.memgraph.yml up -d
   ```
   Verify Bolt is answering (this is the P1 compose smoke). First confirm the
   container is the thing listening on 7687 (`docker ps | grep jcyber-memgraph`;
   `lsof -i:7687` should point at Docker, not a stray native Memgraph/Neo4j) so
   the smoke can't pass against an unrelated server:
   ```
   uv run python -m jcyber.clients.memgraph --smoke   # expect: memgraph smoke ok: 1
   ```
   Then apply the schema with `$eid` set, per
   `schema/memgraph/engagement-graph.cypher`.
2. **Hands.** Start the HexStrike server on `127.0.0.1:8888`
   (`python3 hexstrike_server.py`). Only the closed-set tool endpoints in
   `orchestrator/loop.md` section 3 are called; the `/api/intelligence/*` and
   `ai_*`/`bugbounty_*` surface is never touched.
3. **Proxy.** Start Caido on `127.0.0.1:8889` (one above HexStrike) with a
   fresh project whose allow-scope is derived from `scope.toon`. Passive
   plugins only.
4. **Long-term brain.** Start the standalone SQLite memory-core (PLAN D1
   option b) and point `JCYBER_MEMORY_URL` at it:

   ```
   uv run python deploy/memory_core.py 8130 ~/.jcyber/memory.db
   export JCYBER_MEMORY_URL=http://127.0.0.1:8130
   ```

   It speaks the same 2-method seam (`/recall`, `/commit`) as hosted
   TencentDB, so the backend swaps without touching the loop.

## Intake

Bare link (no scope items):

```
uv run python -m jcyber intake <link>              # bare-link default
uv run python -m jcyber intake <link> --sev high   # explicit severity focus
```

This writes `$JCYBER_HOME/<slug>/scope.toon` - a full scan of the target
(apex host plus all subdomains), 5 rps, critical-only report focus. A
leading `www.` is stripped from the scope host, so the apex domain (and its
sibling subdomains) are in scope, not just `www.*`. TOON is always
`@toon-format/cli` output (Node required), never hand-formatted. Then
author `engagement.toon` (JSON shape: `schema/storage-layout.md`) and run.

Explicit scope: write encoder-produced `engagement.toon` and `scope.toon` by
hand (shapes in `schema/storage-layout.md`); both are `@toon-format/cli`
output.

## Run

```
uv run python -m jcyber engagements/<slug>
```

The entrypoint loads the config, recalls priors once, and drives the bounded
loop (`observe -> decide -> gate -> act -> store -> learn`) until the
engagement is report-ready, `commit` is chosen, three consecutive gates make
no progress, or the tool-run budget is spent.

## What is exercised only here

The following seams are wired but verified live, under supervision — not in
CI:

- Jev decisions against the real TypeSafe API.
- HexStrike tool runs and Caido passive findings ingestion.
- Cerebras engine augmentation (`route_via_engine`), when `engine.enabled`.
- TencentDB recall at intake and commit at close.
- G3 finding scoring (severity/bounty) and report rendering.

Stop and escalate to a human on any scope ambiguity, any below-floor
`scope_safe`, or any operator-confirm (`confirm_parked`) gate outcome.
