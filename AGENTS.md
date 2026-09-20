# Agent conventions — Jcyber

Repo: the **plan** for an agent-driven bug bounty / pentesting framework
chaining HexStrike (hands), Jev (reflex), Memgraph (session brain),
TencentDB Agent Memory (long-term brain), Prometheus harness (doctrine).
Docs-first: the load-bearing artifacts are the specs, not the code.

## Load-bearing invariants (do not violate when editing this repo)

1. **TOON everywhere machine-written config/state lives.** Every
   `.toon` file is *encoder output* — produced by `@toon-format/cli` from
   JSON, never hand-formatted. Canonical examples: `schema/storage-layout.md`.
   Validate any changed file: `npx -y @toon-format/cli <file>` (must parse
   and round-trip; `[N:]` / `{fields}` declarations stay consistent with the
   JSON they encode).
2. **Thresholds have one home per doc set and are byte-identical across
   files.** Canonical set (verify against `config/decision-catalog.md`
   before changing any one): per-class auto gates
   `recon_passive 0.80 / recon_active 0.85 / probing 0.90 / verify 0.90 /
   fuzzing 0.95 / report 0.95` (else `queue` for recon, `confirm` for
   probing/fuzzing/report/exploit, `verify` re-decides next iteration);
   `scope_model_floor 0.90`;
   hypothesis verdicts `promote ≥ 0.80`, `retire ≤ 0.20` (noul support);
   `report_ready ≥ 0.95`. A change propagates: catalog, `engagement.toon`
   (+ its JSON), `loop.md`, `examples/idor-walkthrough.md` — all at once,
   or not at all.
3. **Scope gate is two layers, both mandatory.** Deterministic string match
   against `scope.toon` (no model, non-jailbreakable) *and* `scope_safe`
   noul ≥ 0.90. Out-of-scope always wins conflicts. A spec edit that gives
   either layer a way to be bypassed is wrong, even if it looks more "agent
   friendly."
4. **Jev is the only model in the control path, and it is atomic.**
   One `system_one(state, questions)` per loop iteration; every question is
   a single gut-check (`choice`/`noul`/`score`); **composites are combined
   in code with explicit weights** (e.g. report priority =
   `0.7·severity + 0.3·bounty`), never asked to the model as one
   question. Don't add a question; extend the catalog.
5. **No free-form command construction.** HexStrike calls are
   (tool-name, closed-set params) — target/account from `scope.toon`,
   surface from the graph, sets from config. Jev answer text never reaches
   a shell, a command string, a path, or a URL. `orchestrator/loop.md`
   §4 is the reference for how this is enforced.
6. **TencentDB is read at recall, written at commit** (one two-method
   seam, `schema/tencentdb/memory-interface.md`). Nothing in the loop
   touches it mid-run; it is swappable (standalone backend today, hosted
   later).
7. **HexStrike is the hands only.** Never invoke its `/api/intelligence/*`
   or `bugbounty_*`/`ai_*` MCP tools — a second decision layer in the loop
   is exactly the failure mode this architecture prevents. Source-verified:
   v6's "Intelligent Decision Engine" and its 12+ "AI agents" are hard-coded
   heuristics (no model, no BYOK, no LLM plumbing). Jcyber's BYOK engine is
   *ours*: a Jev-dispatched tool under one atomic catalog question
   (`route_via_engine`), Cerebras via operator env `CEREBRAS_API_KEY`, model
   pin in `engagement.toon` (`engine.model`), output evidence-only, recorded
   on the `:Decision` node — never an autonomous layer.

## Repo layout (what goes where)

| Path | What | Rule |
|---|---|---|
| `PLAN.md` | the five-component chain, phases, risks | architecture truth |
| `README.md` | orientation + layout manifest | keep the manifest in sync when files land |
| `schema/storage-layout.md` | on-disk engagement layout, TOON shapes (canonical) | scope/engagement TOON blocks are the reference encodings |
| `schema/memgraph/engagement-graph.cypher` | node/label + index DDL, invariants, state-projector shape | Cypher must match Memgraph docs (unnamed point indexes `CREATE INDEX ON :Label(props)`) |
| `schema/tencentdb/memory-interface.md` | 2-method seam | the only contract with the long-term brain |
| `config/decision-catalog.md` | all Jev questions + gate thresholds | the "heart of the chain" |
| `orchestrator/loop.md` | loop pseudocode + `next_action` → HexStrike tool routing | tool names must match `hexstrike_mcp.py` (HexStrike v6) |
| `deploy/docker-compose.memgraph.yml` | P1 session brain (Memgraph :7687 + Lab :3000) | schema is applied per engagement, never baked into images |
| `examples/idor-walkthrough.md` | one finding (AC-001) traced through all five components | example must stay consistent with every spec file |
| `engagements/` | live engagement state (in the future) | **gitignored — never committed** |
| `docs/` | `diagrams.md` (Mermaid: stack + decision gate), `FAQ.md` (FAQ + comparison vs other pentest tools), `RUNBOOK.md` (live bring-up) | diagrams are the canonical source the README/PLAN link to |
| `jcyber/` | Python runtime: reflex core (loop, gates, scope, normalizer, state) + adapters in `jcyber/clients/`; bare-link intake (`jcyber/intake.py` — scope-only synthesis) | **no gate values in code** (invariant #2); TOON via the codec port only (invariant #1) |
| `tests/` | pytest: deterministic-gate safety, loop replay, live-Memgraph integration | canonical fixtures mirror `schema/storage-layout.md` JSON; real loaders, fakes elsewhere |
| `scripts/check_docs.sh` | docs-invariants gate: TOON round-trip, threshold identity, mermaid sync, README manifest, links | must pass before any push; it is the enforcement of invariants #1 and #2 |
| `.github/workflows/ci.yml` | CI: lint + pyright + pytest, docs gate, Memgraph smoke | CI is the enforcement gate; pre-commit hooks are a local mirror only |

`CLAUDE.md` mirrors this file (Claude Code entry point); keep them in
sync.

## Example engagement identity (stay consistent)

The walkthrough uses, and any new example must reuse: slug `acme-lab`,
target `acme-lab.example`, IDs `H-###` / `E-###` / `F-###` / `VF-###` /
`AC-###` (sequential per engagement, never reused — Prometheus doctrine),
raw files `evidence/raw/<sha256>.<ext>`, outbox
`learnings/{atoms.md,skills.md,scenario.md,status.toon}`.

## Docs discipline

- Every claim about an external system (Memgraph, HexStrike, TencentDB,
  TypeSafe Jev) must match its current docs/source — re-fetch before
  correcting; don't "fix" a statement based on memory of an old doc.
- Keep the five components' roles from `PLAN.md` §2 (Owns / Does NOT do) —
  a component doing a job another component owns is a plan regression.