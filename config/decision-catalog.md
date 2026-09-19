# Jev decision catalog

The complete set of atomic questions the orchestrator may ask each loop
iteration. One `system_one(state, questions)` call per iteration; the question
list is assembled from this catalog **in code**, never by the model.

## Request shape

```json
{
  "state":   "<compact text projection of the Memgraph state, see below>",
  "model":   "jev-latest",            // pinned per engagement (engagement.toon)
  "questions": {
    "next_action": { "type": "choice",
                     "instructions": "...",
                     "criteria": { "option": "when this option is right", ... } },
    "scope_safe":  { "type": "noul",
                     "instructions": "...",
                     "criteria": { "true": "...", "false": "..." } },
    "severity_f_002": { "type": "score",
                        "instructions": "...",
                        "criteria": ["worst", "...", "best"] }
  }
}
```

- `state` is text-only, English-primary, ≤ `state_budget_chars`
  (default 24000, per `engagement.toon`). It is produced by the state
  projector — ids + one-line summaries, never raw payloads.
- Each question is answered under `answers.<qid>`:
  - `choice` → chosen option + `probabilities` (per option) + `confidence`
  - `score`  → level index + `probabilities` (per level) + `confidence`
  - `noul`   → single value ∈ [0,1] (+ optional `confidence`) — "natural
    probability", the model's intrinsic belief without calibration pressure
- All three types mix freely in one request. Each question is one gut-check:
  never a multi-factor task. **Composite judgments are assembled in code**
  (e.g. report priority = `0.7·severity + 0.3·bounty`), each input its own
  atomic question.

## The state (what `state` contains)

Built by the projector from the engagement graph (bounded — top-N by
timestamp, capped at `state_budget_chars`):

```
engagement: acme-lab  target: acme-lab.example  phase: active_probing
budget: 11h of 24h used, 213/500 jev_calls, 188/300 tool_runs
scope (verified deterministic match, authoritative):
  in: acme-lab.example, *.acme-lab.example, acme-lab.example/api/, 203.0.113.0/24
  out: staging.acme-lab.example, acme-lab.example/pay/
  constraints: 5 rps, 08:00-20:00 UTC, no fuzzing on /checkout /pay
open hypotheses:
  H-003 GET /api/users/{id} returns full profile for any id (support 0.83)
  H-004 /admin path excluded from scope but referenced in JS bundle (support 0.41)
provisional findings:
  F-002 user enumeration via /api/auth/check (severity 2, bounty 1)
  F-011 IDOR read on /api/users/{id} (severity 3, bounty 3)   <-- PoC pending
validated findings:
  VF-001 API key in JS bundle v2.4.1 (severity 4, bounty 3, reported)
evidence (last 12):
  E-041 sqlmap /api/users/?id=1 → time-based boolean blind, 200 rows dumped   [sha a3f1…]
  E-042 nuclei acme-lab.example → xss-reflected on /api/search?q=              [sha 9c02…]
  E-043 gobuster acme-lab.example/api/ → /admin 403, /internal 200              [sha 77ab…]
attack chains:
  AC-001 user enumeration → IDOR → bulk data exposure (demonstrated, 3 steps)
operator notes:
  - "test accounts are jcyber-test1@/test2@"
  - "do not touch staging"
priors (from long-term memory):
  - skill: subdomain takeover of dormant wildcard CNAMEs (success)
  - atom: this vendor runs F5 BIG-IP (last engagement, 2025-11)
```

## The questions

Thresholds below are the **canonical values** — identical in
`schema/storage-layout.md` and `orchestrator/loop.md`. All defaults; each
engagement may raise them, never lower them below floor.

### G0 — Scope gate (asked for EVERY action, before any action)

| qid | type | instructions (abridged) | criteria | gate |
|---|---|---|---|---|
| `scope_safe` | noul | "Given the authoritative in/out scope lists, how likely is this specific proposed action (tool, target, params) unambiguously within scope?" | true: "clearly in-scope, no out-of-scope match" · false: "touches out-of-scope host/path, ambiguous ownership, or needs interpretation" | **noul ≥ 0.90** (`scope_model_floor`), else `queue`. The deterministic string gate runs first; this is layer 2 and never replaces it. |

Out-of-scope always wins conflicts. A `false`-leaning answer is **not** a
rejection — it is a queue item for the operator with the reasoning attached.

### G1 — Action selection (asked once per iteration)

| qid | type | instructions | criteria (option → description) | gate |
|---|---|---|---|---|
| `next_action` | choice | "Which single next action best advances the engagement given the state?" | `recon_passive` → enumerate without touching the target (subdomains, historical URLs, OSINT) · `recon_active` → contact the target lightly (port scan, tech fingerprint, wordlist dirb) · `probing` → targeted test of a specific open hypothesis (vuln class probe, parameter test) · `fuzzing` → high-volume payload/param fuzzing against a confirmed attack surface · `verify` → re-run a minimal PoC to confirm a finding still holds · `exploit` → active exploitation already authorized by the operator · `report` → stop probing, prepare report · `commit` → nothing left productive; distill and close | Auto-gates by action class (see table below) on the answer's **own confidence**. Low confidence + `exploit`/`fuzzing` → always `confirm`, never auto. |
| `skill_pick` (asked only when the recalled skill list is non-empty AND one of its trigger boundaries matches the current state) | choice | "Which recalled skill, if any, should this action follow? Each option's description is the skill's trigger boundary and its validation rule. Do not force a fit — `none` is a real option." | one option per recalled skill id (description = its trigger boundary + validation rule) + `none` → "no recalled skill applies to this action" | No gate of its own. The selected skill only restructures the parameter set of the already-gated action (e.g. the sequential-ID IDOR skill supplies the account-swap step and the second-account confirmation). A skill never bypasses `scope_safe` or a class gate. |

**Action-class auto thresholds** (confidence of the chosen option):

| class | auto if conf ≥ | else |
|---|---|---|
| recon_passive | 0.80 | queue |
| recon_active | 0.85 | queue |
| probing | 0.90 | confirm |
| fuzzing | 0.95 | confirm |
| report | 0.95 | confirm |
| exploit | 0.95 | confirm |
| skill via `skill_pick` | (n/a) | follows the class gate of the action it parameterizes |

Below-threshold recon goes to `queue` (operator can bulk-approve); below-
threshold probing/fuzzing/report go to `confirm` (single approval, parking the
action with full audit record). Any action failing `scope_safe` → `block`, no
queue.

### G2 — Hypothesis lifecycle (asked when new evidence lands or an H is aged)

| qid | type | instructions | criteria | gate |
|---|---|---|---|---|
| `h_<id>_supported` (one per open H with fresh evidence) | noul | "Given the evidence attached to H-###, how likely is H-### true?" | optional true/false rubric: supported vs falsified | support ≥ **0.80** → auto **promote** (H→F provisional). support ≤ **0.20** → auto **retire** (record cause). Band 0.20–0.80 → stays open; one more probe decision allowed per evidence batch, then forced retire-or-promote revisit at next iteration. |
| `e_class_<new_evidence>` | choice | "Is this new evidence a new fact, a duplicate of an existing one, or an extension of it?" | `new` → insert as fresh E-### · `duplicate` → link `DUP_OF`, return existing id · `extension` → attach to existing E-###, update summary | Deterministic pre-check first (sha256 + vector top-k similarity); only *ambiguous* items (similarity between 0.75 and 0.95, or same target+tool but different outcome) reach Jev. |
| `chain_probe` (asked only when ≥1 demonstrated/confirmed partial chain exists) | noul | "How likely does this partial chain extend into a materially more severe one?" | — | ≥ 0.80 → orchestrator emits a `probing`-class follow-up targeting the chain's next hop automatically (subject to G0 + class gate). |

### G3 — Finding assessment (asked when a provisional F is confirmed, or updated)

| qid | type | instructions | criteria (ordered, worst→best) | gate |
|---|---|---|---|---|
| `severity_f_<id>` | score | "Rate real-world severity of F-### for this target, considering data sensitivity, exploit reliability, and breadth of affected users; be conservative — the evidence, not the category, decides." | 0 none/negative · 1 low (info disclosure, minor) · 2 medium (needs chaining, limited impact) · 3 high (reliable access to sensitive data or functions) · 4 critical (auth bypass → full account compromise, RCE, bulk PII) | Feeds report. No auto action; recorded on the :Finding node; operator can override with reason (recorded on the node). |
| `bounty_f_<id>` | score | "Rate likely program payout relative to typical bug-bounty tiers for this class and impact, from the program's perspective." | 0 not paid (policy/out-of-class) · 1 $0–500 · 2 $500–5k · 3 $5k+ / top-tier | Feeds report priority composite. |
| `report_priority_ranking` — **not asked to Jev.** | — | — | — | Composite in code: `priority = 0.7·severity + 0.3·bounty`. Asking one question for a weighted sum violates decision atomicity. |

### G4 — Termination

| qid | type | instructions | criteria | gate |
|---|---|---|---|---|
| `report_ready` | noul | "Is the engagement in a state where a defensible report can be produced now? (Every validated finding has linked evidence + reproducible PoC; no high-support open hypothesis is being abandoned; chains are either demonstrated or explicitly dead-ended.)" | true: "all of the above hold" · false: "any VF missing PoC, or open H with support ≥0.6 unexplored" | **≥ 0.95** → proceed to report render (with `confirm` by default at this gate class — operator signs the report). Below → orchestrator keeps looping; if below **twice consecutively with no state change**, it halts with a diagnostic (`ycb doctor <slug>` output attached) instead of burning budget. |

## Budgets & halts (code-side, no Jev involvement)

| condition | behavior |
|---|---|
| `wallclock_hours` exhausted | halt; state → `handed_off`; report render only if `report_ready` passed earlier |
| `jev_calls` exhausted | same |
| `tool_runs` exhausted | same |
| 3 consecutive gate failures (scope or confidence) on distinct targets | halt with diagnostic — pattern suggests scope drift or misconfig |
| `report_ready` < threshold twice with unchanged state | halt with diagnostic (see G4) |

## Audit

Every iteration's call is recorded as a `:Decision` node (see
`schema/memgraph/engagement-graph.cypher`): `state_hash`, the exact question
ids asked, typed `answers_json` incl. probabilities/confidences, both gate
values, and `outcome ∈ auto|confirm_parked|blocked|halted`. The full decision
history is replayable — no decision in an engagement is an artifact of
unrecorded model state.