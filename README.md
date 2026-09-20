# Jcyber

[![CI](https://github.com/undeemed/Jcyber/actions/workflows/ci.yml/badge.svg)](https://github.com/undeemed/Jcyber/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

**An agent that runs bug-bounty and pentest engagements as one gated chain.**
Every action is checked against a deterministic scope gate **and** a confidence
gate before it fires - nothing runs on vibes, nothing runs out of scope.

Jcyber is not another autonomous scanner. It wires five systems into a single
decision loop: it recalls what it learned on past targets, reads the live state
of the current engagement, asks one fast model a batch of typed questions,
checks each answer against scope + confidence gates, and only then runs a
security tool. Every fact lands in a graph; every finding traces from raw
evidence back to the report.

> **New here?** Start with [Quick start](#quick-start) below.
> Want the full design → [`PLAN.md`](PLAN.md).
> Want to see one real finding traced end to end →
> [`examples/idor-walkthrough.md`](examples/idor-walkthrough.md).

## How it works

```
RECALL  TencentDB -> priors + skills from past engagements
OBSERVE Memgraph  -> compact state snapshot of this engagement
DECIDE  Jev       -> one system_one() call, many atomic questions -> typed answers + confidence
GATE    Router    -> deterministic scope check AND confidence thresholds -> auto / confirm / block
ACT     HexStrike -> run the chosen MCP tool -> raw output
PROXY   Caido     -> target traffic logged + passive-plugin checked (127.0.0.1:8889)
STORE   Normalizer-> raw to vault, one-line summary to Evidence node, embed to vector index
LEARN   Memgraph  -> graph updated (H->E->F->AC); durable atoms enqueued out to TencentDB
```

**Every decision is a typed question with a confidence score. Every fact lives
in the graph. Every finding traces from raw evidence to report. Every action
passes scope + confidence gates before execution.**

## The systems

Five systems chained into the loop, plus Caido as the traffic substrate:

See [how each service is used](docs/diagrams.md#service-usage-per-iteration) for the per-iteration flow.

| Component | Source | Role |
|---|---|---|
| **HexStrike AI** | [0x4m4/hexstrike-ai](https://github.com/0x4m4/hexstrike-ai) | **Hands** - 150+ security tools behind an MCP server. Driven, not autonomous. |
| **Caido** | [caido.io](https://caido.io) | **Traffic substrate** (infra, not a sixth system) - MITM proxy pinned at `127.0.0.1:8889` (one off HexStrike). Logs all target traffic, plugin-checked (Autorize/Scanner passive), edit-and-replay. Its verdicts enter as evidence, never as decisions. |
| **Jev (TypeSafe)** | [docs.typesafe.ai](https://docs.typesafe.ai/introduction.md) | **Reflex** - fast, structured, confidence-calibrated decisions (choice / score / noul). The only model in the control path. |
| **Memgraph** | [memgraph/memgraph](https://github.com/memgraph/memgraph) | **Session brain** - live per-engagement graph: scope, assets, findings, evidence, attack chains, decisions. Vector index for dedup. |
| **TencentDB Agent Memory** | [TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory) | **Long-term brain** - L0->L3 distillation, reusable skills, wiki of vendors, cross-engagement recall. |
| **Prometheus Pentest Harness** | [N0tMilk/prometheus-pentest-harness](https://github.com/N0tMilk/prometheus-pentest-harness) | **Doctrine** - not a runtime. Its ID model (H-### / E-### / F-### / VF-### / AC-###), evidence-first lifecycle, and engagement layout are compiled into Jcyber's schema and gates. |

## Requirements

The deterministic build (tests, docs gate) needs only the toolchain; the live
loop needs the services and secrets below.

### Toolchain
- **Python 3.12+** and [`uv`](https://docs.astral.sh/uv/)
- **Docker** - runs the Memgraph session brain
- **Node** - `intake` shells out to `npx @toon-format/cli` (TOON is always encoder output)

### Services (live path)
- **Memgraph** - `docker compose -f deploy/docker-compose.memgraph.yml up -d` (Bolt `:7687`, Lab `:3000`)
- **HexStrike** - clone [0x4m4/hexstrike-ai](https://github.com/0x4m4/hexstrike-ai) and boot `hexstrike_server.py`. Boot deps (Python 3.12 venv): `flask psutil requests aiohttp beautifulsoup4 selenium mitmproxy` - it does **not** need `angr`/`pwntools` (those appear only inside exploit-template strings). **Port collision:** HexStrike defaults to `:8888`, the same port as Caido's API - run it elsewhere with `HEXSTRIKE_PORT=8899` and point `HEXSTRIKE_URL` at it.
- **Security tools** HexStrike wraps - install the ones your `engagement.toon` routes: `nmap`, `httpx`, `nuclei`, `ffuf`, `subfinder`, `katana`.
- **Caido** - `caido-cli --no-open --listen 127.0.0.1:8888` (GraphQL API + UI); the MITM proxy runs on `:8889` per project. Findings are pulled over the API.
- **memory-core** - the standalone SQLite long-term brain: `uv run python deploy/memory_core.py 8130 ~/.jcyber/memory.db`.

### Secrets (local `.env`, gitignored)
- `TYPESAFE_API_KEY` - **required**; Jev is the only model in the control path.
- `CAIDO_API_TOKEN` - a Caido **access token** for the instance API (only needed to ingest Caido findings). Caido auth is a PAT-driven OAuth device flow: create a Personal Access Token at [dashboard.caido.io](https://dashboard.caido.io/developer), exchange it for an access token (e.g. via [`@caido/sdk-client`](https://developer.caido.io/client-sdk/guides/base_setup.html)), and store that access token here.
- `JCYBER_MEMORY_URL` - memory-core URL, e.g. `http://127.0.0.1:8130`.
- `CEREBRAS_API_KEY` - optional; only if the BYOK engine is enabled in `engagement.toon`.

### Ports
| Service | Port | Notes |
|---|---|---|
| Memgraph Bolt | `7687` | session brain |
| Memgraph Lab | `3000` | graph UI |
| HexStrike REST | `8899` | default `8888` collides with Caido; move via `HEXSTRIKE_PORT` |
| Caido API | `8888` | findings GraphQL + UI |
| Caido proxy | `8889` | MITM traffic (per project) |
| memory-core | `8130` | SQLite long-term brain |

Full bring-up: [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Quick start

Run these in order. Steps 1-3 need no secrets; the live run (step 6) needs `TYPESAFE_API_KEY` in `.env`.

**1. Install.**

```
uv sync
```

**2. Start the session brain (Memgraph).**

```
docker compose -f deploy/docker-compose.memgraph.yml up -d
uv run python -m jcyber.clients.memgraph --smoke   # expect: memgraph smoke ok: 1
```

**3. Apply the engagement schema** to the fresh container (per `schema/memgraph/engagement-graph.cypher`).

**4. Create an engagement from a link.** A bare link is enough - it resolves to
a full scan of the target (apex host plus all subdomains), 5 rps, critical-only
report focus:

```
uv run python -m jcyber intake https://acme-lab.example
# -> engagements/acme-lab-example/scope.toon   (--sev none|low|medium|high|critical to change focus)
```

**5. Author `engagement.toon`** next to the generated `scope.toon` (gates,
verdicts, Jev pin, budgets - JSON shape in [`schema/storage-layout.md`](schema/storage-layout.md)).
Intake writes the scope only; the code holds no gate values.

**6. Run the loop** (loads secrets from `.env`):

```
uv run --env-file .env python -m jcyber engagements/acme-lab-example
```

For an explicit scope instead of a bare link, hand-author both `scope.toon` and
`engagement.toon` (both shapes in `schema/storage-layout.md`); both must be
`@toon-format/cli` output, never hand-formatted.

## Status

| Phase | State |
|---|---|
| P0 skeleton (schema, decision catalog, loop spec, example) | done |
| P1 session brain (Memgraph compose + smoke) | done - CI Memgraph smoke green; engagements created, projected, and driven (decisions, evidence, verdicts) live against the container |
| P2 live hands (HexStrike + Caido) | done - live: one Loop iteration drove a real HexStrike `nmap` run on an in-scope localhost target into an `E-###`, with the Caido proxy param on the call; endpoint map + Caido GraphQL query verified against upstream source |
| P3 reflex core (loop, gates, scope, normalizer, state, intake) | done - live: a 10-iteration loop self-selects via real Jev, writes 10 `:Decision` nodes, and halts on an out-of-scope fixture (deterministic block, no target contact) |
| P4 long-term brain (TencentDB seam) | seam done - live round-trip through the standalone SQLite memory-core (commit at close, recall on the next run); the PLAN §8 N+1-faster measurement is future work |
| P5 operator UX | report + trace done - `jcyber report <dir>` (Markdown from the graph) and `jcyber trace <dir>` (per-iteration `:Decision` audit); TUI/dashboard over Memgraph Lab remains |

The live path (real Memgraph/HexStrike/Jev/memory-core) was demonstrated this
session on an in-scope localhost target; it is not run in CI (needs the Jev key
and the external services). CI covers lint, types, tests, the docs gate, and a
Dockerized Memgraph smoke.

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

## Layout

~~~text
jcyber/                          reflex core - no gate values in code
├─ loop.py  gate.py  scope.py       observe->decide->gate loop + deterministic scope match
├─ decide.py  state.py  router.py   Jev question assembly, state projector, tool routing
├─ normalize.py  learn.py           raw -> E-### evidence; distiller (atoms/skills)
├─ report.py  trace.py              Markdown report + decision-audit trace renderers
├─ config.py  types.py  ports.py    engagement/scope loaders, typed model, port protocols
├─ intake.py  __main__.py           bare-link scope synthesis; CLI (run/intake/report/trace)
└─ clients/                         one adapter per external system
   ├─ hexstrike.py  caido.py        hands (tool REST) + proxy (findings GraphQL)
   ├─ jev.py  engine.py             decision model (Jev) + BYOK engine (Cerebras)
   └─ memgraph.py  tencentdb.py  toon.py   session graph, long-term-brain seam, TOON codec
tests/                           pytest: gate safety, loop replay, live Memgraph integration
config/decision-catalog.md       the Jev question catalog (the heart of the chain) + gates
orchestrator/loop.md             loop pseudocode + next_action -> HexStrike tool routing
schema/
├─ storage-layout.md             on-disk engagement layout (canonical scope/engagement TOON)
├─ memgraph/engagement-graph.cypher   graph schema, indexes, invariants, state projector
└─ tencentdb/memory-interface.md      the 2-method long-term-brain seam (recall / commit)
deploy/
├─ docker-compose.memgraph.yml   session brain (Memgraph + Lab)
└─ memory_core.py                standalone SQLite long-term brain
docs/
├─ diagrams.md                   architecture, decision-gate + service-usage diagrams (Mermaid)
├─ RUNBOOK.md                    operator bring-up + intake + run + report/trace
└─ FAQ.md                        FAQ + how Jcyber compares to other pentest tools
scripts/check_docs.sh            docs-invariants gate (TOON, thresholds, mermaid, manifest, links)
examples/idor-walkthrough.md     one finding (AC-001) traced end-to-end through all five systems
PLAN.md                          the full chain plan: architecture, loop, phases, risks
AGENTS.md / CLAUDE.md            agent conventions for working in this repo (mirrored)
.github/workflows/ci.yml         CI: lint/type/test, docs gate, Memgraph smoke
pyproject.toml                   package config (uv, ruff, pyright, pytest)
~~~

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md): run the four gates before pushing, and write [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Invariants live in [`AGENTS.md`](AGENTS.md).

## Legality

Jcyber assumes **in-scope targets only**. The scope gate is load-bearing, not decorative: it is deterministic (`scope.toon` string match) **and** modeled (Jev noul ≥ 0.90), and it halts automatically on below-threshold confidence. See the [legal note](docs/FAQ.md#legal-note) in the FAQ.

## License

MIT - see `LICENSE`.
