# Jcyber

Agent-driven Bug Bounty / Pentesting Framework.

Five systems, one chain:

| Component | Source | Role |
|---|---|---|
| **HexStrike AI** | [0x4m4/hexstrike-ai](https://github.com/0x4m4/hexstrike-ai) | **Hands** — 150+ security tools behind an MCP server. Driven, not autonomous. |
| **Jev (TypeSafe)** | [docs.typesafe.ai](https://docs.typesafe.ai/introduction.md) | **Reflex** — fast, structured, confidence-calibrated decisions (choice / score / noul). The only model in the control path. |
| **Memgraph** | [memgraph/memgraph](https://github.com/memgraph/memgraph) | **Session brain** — live per-engagement graph: scope, assets, findings, evidence, attack chains, decisions. Vector index for dedup. |
| **TencentDB Agent Memory** | [TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory) | **Long-term brain** — L0→L3 distillation, reusable skills, wiki of vendors, cross-engagement recall. |
| **Prometheus Pentest Harness** | [N0tMilk/prometheus-pentest-harness](https://github.com/N0tMilk/prometheus-pentest-harness) | **Doctrine** — not a runtime. Its ID model (H-### / E-### / F-### / VF-### / AC-###), evidence-first lifecycle, and engagement layout are compiled into Jcyber's schema and gates. |

## Core idea

```
RECALL  TencentDB → priors + skills ──────────────────┐
OBSERVE Memgraph → compact state snapshot ────────────┤
DECIDE  Jev: one system_one() call, many atomic questions ─→ typed answers + confidence
GATE    deterministic scope check AND confidence thresholds  ─→ auto / confirm / block
ACT     HexStrike MCP tool  ─→ raw output
STORE   Normalizer: raw→vault, summary→Evidence node, embed→vector
LEARN   Memgraph graph updated (H→E→F→AC); durable atoms enqueued out → TencentDB
```

**Every decision is a typed question with a confidence score. Every fact lives in the graph. Every finding traces from raw evidence to report. Every action passes scope + confidence gates before execution.**

## Layout

- `PLAN.md` — the full chain plan: architecture, loop, phases, risks, open decisions
- `AGENTS.md` / `CLAUDE.md` — agent conventions for working in this repo
  (TOON-first config, threshold consistency, scope gate, decision atomicity,
  no free-form command construction)
- `schema/storage-layout.md` — on-disk engagement layout + what goes where
  (canonical `scope.toon` / `engagement.toon` encodings)
- `schema/memgraph/engagement-graph.cypher` — engagement graph schema,
  indexes, invariants, state projector shape
- `schema/tencentdb/memory-interface.md` — the 2-method seam (recall /
  commit) with the long-term brain
- `config/decision-catalog.md` — the Jev question catalog (the heart of the
  chain) with confidence gates
- `orchestrator/loop.md` — the control loop, pseudocode +
  `next_action` → HexStrike tool routing
- `deploy/` — docker compose for the session brain (Memgraph + Lab)
- `examples/idor-walkthrough.md` — one finding (AC-001) traced end-to-end
  through all five components

## Status

Planning phase. See `PLAN.md` §Phases for the build sequence.

## Legality

Jcyber assumes **authorized, in-scope targets only** (bug bounty programs, owned systems, signed engagements). The scope gate is load-bearing, not decorative: it is deterministic (`scope.toon` string match) **and** modeled (Jev noul ≥ 0.90), and it halts automatically on below-threshold confidence.