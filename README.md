# Jcyber

[![CI](https://github.com/undeemed/Jcyber/actions/workflows/ci.yml/badge.svg)](https://github.com/undeemed/Jcyber/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

**Agent-driven Bug Bounty / Pentesting Framework** - one gated chain over five
systems: an MCP-driven toolbox (HexStrike), atomic confidence-calibrated
decisions from a single fast model (Jev/TypeSafe), a live graph per
engagement (Memgraph), cross-engagement memory (TencentDB Agent Memory), and
doctrine (Prometheus pentest harness). Every action passes a deterministic
scope gate **and** a confidence gate before it executes.

| Component | Source | Role |
|---|---|---|
| **HexStrike AI** | [0x4m4/hexstrike-ai](https://github.com/0x4m4/hexstrike-ai) | **Hands** - 150+ security tools behind an MCP server. Driven, not autonomous. |
| **Jev (TypeSafe)** | [docs.typesafe.ai](https://docs.typesafe.ai/introduction.md) | **Reflex** - fast, structured, confidence-calibrated decisions (choice / score / noul). The only model in the control path. |
| **Memgraph** | [memgraph/memgraph](https://github.com/memgraph/memgraph) | **Session brain** - live per-engagement graph: scope, assets, findings, evidence, attack chains, decisions. Vector index for dedup. |
| **TencentDB Agent Memory** | [TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory) | **Long-term brain** - L0→L3 distillation, reusable skills, wiki of vendors, cross-engagement recall. |
| **Prometheus Pentest Harness** | [N0tMilk/prometheus-pentest-harness](https://github.com/N0tMilk/prometheus-pentest-harness) | **Doctrine** - not a runtime. Its ID model (H-### / E-### / F-### / VF-### / AC-###), evidence-first lifecycle, and engagement layout are compiled into Jcyber's schema and gates. |

## Core idea

```
RECALL  TencentDB → priors + skills ──────────────────┐
OBSERVE Memgraph → compact state snapshot ────────────┤
DECIDE  Jev: one system_one() call, many atomic questions ─→ typed answers + confidence
GATE    deterministic scope check AND confidence thresholds  ─→ auto / confirm / block
ACT     HexStrike MCP tool  ─→ raw output
PROXY   Caido (127.0.0.1:8889): target traffic logged + plugin-checked
STORE   Normalizer: raw→vault, summary→Evidence node, embed→vector
LEARN   Memgraph graph updated (H→E→F→AC); durable atoms enqueued out → TencentDB
```

**Every decision is a typed question with a confidence score. Every fact lives in the graph. Every finding traces from raw evidence to report. Every action passes scope + confidence gates before execution.**

## Quick start

```
uv sync                        # Python 3.12+
docker compose -f deploy/docker-compose.memgraph.yml up -d
uv run python -m jcyber.clients.memgraph --smoke   # expect: memgraph smoke ok: 1
```

Apply the engagement schema per `schema/memgraph/engagement-graph.cypher` on
each fresh container.

**Bare-link engagement** (a link is enough: full scan of the target - apex
plus all subdomains - critical-only findings):

```
uv run python -m jcyber intake https://acme-lab.example
# -> engagements/acme-lab-example/scope.toon (full scan, 5 rps, critical focus; --sev to override)
# author engagements/acme-lab-example/engagement.toon   (JSON shape: schema/storage-layout.md)
uv run python -m jcyber engagements/acme-lab-example
```

`intake` shells out to `npx @toon-format/cli` (Node required) - TOON config is
always encoder output, never hand-formatted. For an explicit scope, author
`scope.toon` alongside `engagement.toon` (both shapes in
`schema/storage-layout.md`).

**Env:** `TYPESAFE_API_KEY` (Jev) and `JCYBER_MEMORY_URL` (long-term brain
backend) are required. The live path additionally needs HexStrike REST on
`127.0.0.1:8888` and the Caido proxy on `127.0.0.1:8889`; `CEREBRAS_API_KEY`
only if `engine.enabled` in `engagement.toon`. Full bring-up: `docs/RUNBOOK.md`.

## Testing and docs gate

```
uv run pytest -q                                    # includes live-Memgraph integration
bash scripts/check_docs.sh                          # TOON round-trip, threshold identity, mermaid sync, links
uv run ruff check . && uv run ruff format --check .
uv run pyright                                      # strict
```

CI (`.github/workflows/ci.yml`) runs all of the above on push/PR plus a
Dockerized Memgraph smoke; a local pre-commit mirror exists
(`.pre-commit-config.yaml`, `pre-commit install`).

## Status

| Phase | State |
|---|---|
| P0 skeleton (schema, decision catalog, loop spec, example) | done |
| P1 session brain (`deploy/docker-compose.memgraph.yml` + smoke) | done |
| P3 reflex core: loop, gates, deterministic scope, normalizer, state, router in `jcyber/`, tested in `tests/`, bare-link intake | done |
| P2 live hands (HexStrike + Caido bring-up) and P4 long-term brain (TencentDB) | next, per `PLAN.md` §8 |

The live entrypoint (`python -m jcyber <dir>`) talks to real
Memgraph/HexStrike/Jev/TencentDB and is exercised under operator supervision,
never in CI.

## Layout

- `docs/diagrams.md` - the architecture + decision-gate diagrams (Mermaid)
- `docs/FAQ.md` - FAQ + how Jcyber compares to other pentest tools
- `docs/RUNBOOK.md` - operator bring-up (Memgraph, HexStrike, Caido, memory backend) + intake + run
- `PLAN.md` - the full chain plan: architecture, loop, phases, risks, open decisions
- `AGENTS.md` / `CLAUDE.md` - agent conventions for working in this repo
  (TOON-first config, threshold consistency, scope gate, decision atomicity,
  no free-form command construction)
- `schema/storage-layout.md` - on-disk engagement layout
  (canonical `scope.toon` / `engagement.toon` encodings)
- `schema/memgraph/engagement-graph.cypher` - engagement graph schema,
  indexes, invariants, state projector shape
- `schema/tencentdb/memory-interface.md` - the 2-method seam (recall /
  commit) with the long-term brain
- `config/decision-catalog.md` - the Jev question catalog (the heart of the
  chain) with confidence gates
- `orchestrator/loop.md` - the control loop, pseudocode +
  `next_action` → HexStrike tool routing
- `jcyber/` - runtime: reflex core (loop, gates, scope, normalizer, state, router) + adapters in `jcyber/clients/` - no gate values in code
- `tests/` - pytest: deterministic-gate safety, loop replay, live Memgraph integration
- `scripts/check_docs.sh` - docs-invariants gate (TOON round-trip, threshold identity, mermaid sync, manifest, links)
- `deploy/` - docker compose for the session brain (Memgraph + Lab)
- `examples/idor-walkthrough.md` - one finding (AC-001) traced end-to-end
  through all five components
- `.github/workflows/ci.yml` - CI: lint/type/test, docs gate, Memgraph smoke
- `pyproject.toml` - package config (uv, ruff, pyright, pytest)

## Legality

Jcyber assumes **in-scope targets only**. The scope gate is load-bearing, not decorative: it is deterministic (`scope.toon` string match) **and** modeled (Jev noul ≥ 0.90), and it halts automatically on below-threshold confidence. See the [legal note](docs/FAQ.md#legal-note) in the FAQ.

## License

MIT - see `LICENSE`.