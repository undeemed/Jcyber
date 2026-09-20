# FAQ + how Jcyber compares

## FAQ

**What is Jcyber, exactly?**
A docs-first plan (no runtime code yet) for an agent-driven bug-bounty /
pentest framework that chains five systems into one loop: HexStrike
(hands), Jev (reflex), Memgraph (session brain), TencentDB Agent Memory
(long-term brain), Prometheus (doctrine). `PLAN.md` is the architecture
truth; the loading artifacts are the specs.

**Is Jev the only model in the control path?**
Yes. One `system_one(state, questions)` per loop iteration; every answer is
a typed choice/score/noul with a confidence. The BYOK engine
(Cerebras, default `qwen-3.8-27b`) is an opt-in *evidence* aid
(`route_via_engine`): it can never pick a tool, class, or target, and its
output enters as `:Evidence` through the same dedup/hypothesis gates.
HexStrike's own "AI engine" is never called — it is source-verified
hard-coded heuristics in v6 (PLAN §11).

**BYOK - how do I plug in my own key?**
Put the key in your operator environment (e.g. `export CEREBRAS_API_KEY=…`
or an operator-local `.env` - gitignored, never committed). Then set
`engine.enabled: true` in `engagement.toon` and pin the models there:
`engine.model` (default `qwen-3.8-27b`) and `engine.model_trivial`
(`gpt-oss-120b`, reserved for low-reasoning calls). The key value is never
written into the repo, a `.toon`, or the vault.

**How is scope enforced?**
Two layers, both mandatory: a deterministic string match against `scope.toon`
(no model involved - not prompt-bypassable) **and** Jev's `scope_safe` noul
≥ 0.90. Out-of-scope always wins on conflict. A `block` is recorded as a
`:Decision` node, so a refusal is auditable, not just a dead end.

**Does any LLM text ever reach a shell, path, or URL?**
No. Invariant: no free-form command construction (AGENTS.md #5, enforced in
`orchestrator/loop.md` §4). Tool calls are (tool name, closed-set params):
target from `scope.toon`, attack surface from graph node ids, sets from
config. Jev text only *selects* from closed sets.

**Why Caido, and why 8889?**
Caido is the traffic substrate, not a sixth system: every target-touching
call flows through a pinned local proxy (`127.0.0.1:8889`), so all wire
traffic is logged and passively plugin-checked (Autorize, Scanner). The pin
is `caido-cli --listen 127.0.0.1:8889` — one above HexStrike's own REST
default `:8888` (`HEXSTRIKE_PORT`), so the pair stays adjacent and
collision-free by construction. These are spec defaults/pins, not machine
facts — the operator's own machine may differ.

**Are the two-layer gate and Caido redundant?**
No: the scope gate gates *which actions may run*; Caido passively checks
*what actually went over the wire*. Caido verdicts are evidence that feed
hypotheses — Caido has no edge toward the gate.

**Is anything runnable today?**
The plan is docs-first; the build sequence is P0–P5 in `PLAN.md`. P0–P2
bring up the substrate (HexStrike, Caido, Memgraph); P3 wires the reflex
loop with a scope-violation fixture; P4 the long-term brain; P5 operator UX
(report, confirm queue, SARIF).

**Is Jcyber open source?**
Yes — this repo is MIT-licensed (see `LICENSE`). Component licenses:
HexStrike MIT, strix Apache-2.0, Prometheus harness Apache-2.0, TencentDB
Agent Memory MIT, Caido proprietary (see the comparison below).

## Comparison to other pentest tools

| Dimension | Jcyber | Strix | XBOW | Horizon3 NodeZero | Caido (+ AI) | Classic tooling |
|---|---|---|---|---|---|---|
| **What it is** | Docs-first plan for an agent-driven BB framework (this repo; MIT) | Open-source autonomous AI hacker (Apache-2.0); graph-of-agents in Docker | Commercial autonomous hacker, web-app focused | Commercial autonomous platform, production-safe; compliance posture | Web proxy/toolkit with AI features; open core + paid tiers | Manual scanners/crawlers |
| **Decision control** | Reflex-in-loop (Jev): typed questions + confidences; deterministic gates before any action | LLM picks tools step by step across an agent graph | Autonomously, black-box | Autonomously, with production-safety guardrails | Human drives; AI assists | Human + config files |
| **Scope enforcement** | Two-layer gate (deterministic string match + model noul ≥ 0.90); out-of-scope wins; blocks recorded | Target/authorization config per run | Program-defined scope | Customer-managed; SOC 2 compliance | Per-project request filters | Operator discipline |
| **Memory** | Memgraph session graph + TencentDB cross-engagement brain (recall + distill) | Per-run; no cross-engagement brain | Per-run, vendor-managed | Managed platform history | Per-project history | None |
| **Audit** | `:Decision` nodes in the graph (typed answers + confidences + gate outcome); sha256-named raw evidence | `findings.sarif` (SARIF) + run artifacts | Reports / API exports | Reports with verification loop | Wire-level request history | Per-tool logs |
| **Traffic layer** | Caido (pinned per engagement) + HexStrike 150+ tools | Native Caido integration (partnership, 2026-03) | Proprietary | Proprietary | It *is* the traffic layer | Tool-specific proxies |
| **BYOK** | Operator-key (Cerebras) via env; models pinned per engagement in `engagement.toon` | BYOK LLM config | None (managed models) | None (managed) | None (managed AI features) | n/a |
| **Self-host / CI** | Self-host by design (P0–P5); SARIF export planned for P5 | Docker + headless `strix -n` (exit codes 0/1/2), `llms.txt` docs, coding-agent skills | SaaS / API, vendor-hosted | Managed SaaS | Local binary + server | Local / CI-able |
| **Reporting** | Graph-rendered Markdown per finding; SARIF in P5 | `findings.sarif` + PoCs | Proprietary reports | Proprietary reports | Exports (HTTPQL/JSON/CSV) | Tool-specific output |

Readers: the rows are feature claims from each vendor's current public
docs/site (2026-09); details move fast — re-verify before citing externally.

**How Jcyber differentiates:**

- **The gap it targets is governance, not capability.** The scanners
  (nuclei, ffuf, katana, sqlmap, …) already exist — HexStrike ships 151 of
  them. Jcyber's bet is that what's missing in autonomous offensive testing
  is an *auditable control plane*: every decision a typed, confidence-scored
  question with a recorded outcome, deterministic gates in the hot path,
  and scope you cannot prompt away.
- **Strix is the nearest neighbor** — same Caido traffic layer, both
  agent-driven and CI-fittable. The fork: Strix is an *autonomous run in a
  box* (the model drives); Jcyber is a *reflex-in-loop with a persistent
  memory* (the model answers atomic questions, gates run before, cross-
  engagement learning accumulates). Strix wins on day-one runnability;
  Jcyber is built for the long engagement where "what did the agent decide,
  and why, across engagements" is the question.
- **XBOW / NodeZero are the managed extremes**: end-to-end autonomous with
  exploitation and verification, strong compliance posture — but closed,
  vendor-hosted, no self-hosting, no self-owned model/brain. Jcyber is the
  self-hosted, self-owned counterpart (BYOK brain, BYOK engine), at the cost
  of the operator running the substrate.
- **Caido-with-AI and classic tooling are the manual baselines**: maximal
  surface and control, zero autonomy. Jcyber deliberately *reuses* this
  surface (via HexStrike + Caido) instead of building new scanners — the
  innovation is in the loop, not the tools.

## Borrowed prior art (from Strix research)

Reviewing `strix/strix` (Apache-2.0) for the comparison above surfaced four
patterns worth folding into the build:

- **Knowledge-pack template.** Strix injects a per-target knowledge pack —
  Attack Surface / Methodology / Techniques / Bypass Methods / Validation —
  selecting the top-5 most relevant entries into context. Maps cleanly
  onto Jcyber's TencentDB **Skill** assets: same schema, one recall call,
  boundary text = the option descriptions.
- **Docs split + `llms.txt`.** Strix splits its docs into quickstart / usage
  / tools / integrations fronted by a single `llms.txt` agent entrypoint.
  Adopt when the code phase starts (P3+): `docs/` already keeps specs
  load-bearing, `llms.txt` just indexes them for agents.
- **Local viewer + tokened link** is prior art for open decision
  **D6** (operator interface, PLAN §10): a minimal local web view over the
  engagement with a per-session token, instead of a bespoke TUI.
- **Headless exit codes 0/1/2 + `findings.sarif`** (SARIF 2.1.0) alongside
  Markdown — the CI shape for Jcyber's P5 reporting: exit code signals the
  gate outcome, SARIF feeds pipelines, Markdown stays the human artifact.

## Legal note

Jcyber assumes **in-scope targets only**. The scope gate is
load-bearing, not decorative: it is deterministic (`scope.toon` string
match, operator-authored) **and** modeled (Jev `scope_safe` noul ≥ 0.90,
per `config/decision-catalog.md`), out-of-scope always wins conflicts, and
below-threshold actions park in the operator queue instead of running.
Blocks are recorded as `:Decision` nodes in Memgraph, so an automation
refusing an out-of-scope action leaves an audit trail. Nothing in this repo
grants permission to test any system. Authorization for a target is the
operator's responsibility.