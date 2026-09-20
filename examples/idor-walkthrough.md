# Walkthrough — one IDOR finding, end to end

One finding (`AC-001`) traced through all five components against the real
files in this repo. Same artifact ids, same thresholds, same tool names as
the plan — deliberately no new machinery is introduced here.

**The finding in one line:** on `acme-lab.example/api/`, an unauthenticated
GET `/api/users/{id}` returns the full user profile for any sequential id,
giving bulk PII exposure (email, phone, password-hash-adjacent fields) —
chain: account enumeration → IDOR read → bulk data exposure.

Scenario: engagement `acme-lab`; the scope items `acme-lab.example`,
`*.acme-lab.example`, `acme-lab.example/api/`, `203.0.113.0/24` are defined
by the operator in `scope.toon`; test accounts `jcyber-test1@` /
`jcyber-test2@acme-lab.example` in scope.

## Step 0 — Intake (operator + storage layout)

- `engagements/acme-lab/scope.toon` — the exact TOON block from
  `schema/storage-layout.md` §Scope file shape (encoder output, mirrored into
  `:Scope` nodes).
- `engagements/acme-lab/engagement.toon` — from the same file: gates
  `probing 0.90 / confirm`, budget `wallclock_hours: 24`.
- `deploy/docker-compose.memgraph.yml` up; `schema/memgraph/engagement-graph.cypher`
  run once with `$eid = 'acme-lab'`.
- `tdb.recall('acme-lab', scope)` (memory-interface.md) returns, among other
  things, a **skill**:

  ```
  [skill s-014] sequential-id IDOR probe
    trigger: endpoint with numeric id returns full record; second authorized account available
    procedure: 1 swap id 2 swap Accept 3 confirm on second account
  ```

  → every Jev state carries a `priors` block; the skill's trigger boundary +
  validation rule are pre-staged as a `skill_pick` candidate.

## Step 1 — Decide: the Jev call (decision-catalog.md)

State projector (the commented Cypher in `engagement-graph.cypher`) renders
a ≤ 24000-char text state. Catalog assembly for this iteration:

```python
questions = {
  "next_action":   Q.choice("Which single next action best advances the engagement…",
                   {"recon_active": "...", "probing": "...", "fuzzing": "...", ...}),
  "skill_pick":    Q.choice("Which recalled skill, if any, should this action follow?…",
                   {"s-014": "sequential-id IDOR: swap id, swap Accept, confirm on 2nd account",
                    "none": "no recalled skill applies"}),
  "scope_safe":    Q.noul("How likely is this proposed action unambiguously within scope?"),
  "report_ready":  Q.noul("Is the engagement ready to report?")
}
```

Answer (typed — the loop branches on it, no parsing):

```text
next_action    = probing        (conf 0.93, P: probing 0.93, recon_active 0.04, …)
skill_pick     = s-014          (conf 0.91)
scope_safe     = noul 0.96
report_ready   = noul 0.21
```

## Step 2 — Gate (loop.md §1 invariant 2)

1. **Deterministic:** `GET https://acme-lab.example/api/users/4821` — host
   matches `host: acme-lab.example` *and* `prefix: *.acme-lab.example`; path
   matches `path: …/api/`; matches no `out_of_scope`; within
   `time_window`; not on `no_fuzzing_on` → **pass**. (This layer is string
   matching — no model, cannot be argued.)
2. **Modeled:** `scope_safe` 0.96 ≥ `scope_model_floor` 0.90 → **pass**.
3. **Class gate:** `probing` at conf **0.93 ≥ 0.90** → **auto** (no operator
   prompt; the action is still fully recorded as `:Decision{outcome:auto}`).

A `:Decision` node is written: `state_hash`, the four question ids, full
typed answers with probabilities, both gate values, `outcome: auto`,
`action: probing`, `tool: http_repeater` (the chosen execution tool).

## Step 3 — Act (loop.md §3 routing table)

`skill_pick = s-014` restructures the already-gated action into a
*parameter set*, never into free text. The router builds closed-set calls:

```text
http_repeater           # probing class, preferred tool for exact-request replay
  proxy: 127.0.0.1:8889                               # from config (caido.proxy)
  request: GET https://acme-lab.example/api/users/4821        # account 1's own id
browser_agent_inspect   # establishes test1's real id (its dashboard GET /me)
  proxy: 127.0.0.1:8889
http_repeater           # GET …/users/4822  (swap id)              # skill step 1
  proxy: 127.0.0.1:8889
http_repeater           # GET …/users/4822 Accept: application/json  # skill step 2
  proxy: 127.0.0.1:8889
http_repeater           # GET …/users/4822 as jcyber-test2@       # skill step 3 (confirm)
  proxy: 127.0.0.1:8889
```

Every target string came from `scope.toon` or an established
`:Endpoint`/`E-###` node; the proxy endpoint came from `config`
(`caido.proxy`) — in every case a closed-set slot, never Jev text reaching
the wire.

Raw output: `evidence/raw/9f3c…b21a.json` (name = sha256 of the bytes,
extension from content type). The 4822 response is a full profile JSON for
a user *neither* test account owns:

```json
{ "id": 4822, "email": "m.reyes@example-corp.co", "phone": "+34 6** *** ***",
  "tier": "pro", "created": "2025-09-14T…", "reset_token_hash": "sha256:0a3f…" }
```

## Step 4 — Store (normalizer → Memgraph)

Dedup pipeline (loop.md §2 `normalize`): sha256 not seen → `CALL
vectorSearchknn` / explicit `vector_search` top-k on `evid_vec` (the
768-dim `cos` index from `engagement-graph.cypher`) → no candidate above
0.95 similarity → question `e_latest_class` is a simple **new** (the vector
check was pre-saturation; the Jev question only fires on the *ambiguous
band* 0.75–0.95) → insert:

```cypher
CREATE (e:Evidence {engagement_id:'acme-lab', id:'E-044',
  tool:'http_repeater', target:'acme-lab.example/api/users/4822',
  ts:'2026-09-14T11:32:07Z',
  summary:'GET /api/users/4822 (test1 session) returns full profile of account 4822: idor read, PII incl. email+phone',
  sha256:'9f3c…b21a', raw_path:'evidence/raw/9f3c…b21a.json', vector:[…768]})
```

Hypothesis lifecycle runs on the new evidence (catalog §G2:
`h_003_supported` noul = **0.92** ≥ 0.80 → **promote**, auto):

- `H-003` ("GET /api/users/{id} returns full profile for any id") →
  `status: promoted`, `support: 0.92`.
- F-011 created `(H-003)-[:DERIVES]->(F-011)`, `F-011-[:SUPPORTED_BY]->E-044`,
  `AFFECTS :Endpoint{id: '…/api/users'}` — provisional.
- Second evidence from the 2nd-account confirmation run → `E-045`, `F-011`
  → **validated** as `VF-011` (invariant 1 of the cypher file: validated
  findings must have `SUPPORTED_BY` edges — `ycb doctor` can check this).
- `AC-001` attack chain: `:AttackChain {id:'AC-001', title:'user enumeration → IDOR → bulk PII exposure',
  status:'demonstrated'}` with `:STEP` n=1..3 over the enumeration
  evidence, F-011, and the bulk-dump evidence `E-046` (20 consecutive ids,
  all 200).

`pocs/VF-011.md` is written: exact steps, request, response excerpt,
accounts used, environment — reproducible from the file alone.

## Step 5 — Learn (distiller → outbox → TencentDB)

Close of the engagement (or `ycb learnings export`) flushes the outbox via
`tdb.commit` (memory-interface.md):

```
learnings/atoms.md:
  "acme-lab.example: /api/users/{id} IDOR read; auth check absent on GET; sequential ids 1..N (E-044,E-045,E-046)"
  "acme-lab.example: /api/auth/check enumerates by email (F-002, VF-002)"
learnings/skills.md:     # s-014 re-validated: last validated 2026-09-14
learnings/scenario.md:   phase reporting; done: recon, auth-bypass, IDOR chain;
                         abandoned: /pay/ (out of scope); 1 chain demonstrated
```

Next time this scope (or this vendor) is recalled, the priors block already
contains the IDOR fact — step 3 above becomes near-instant.

## Step 6 — Report (gate + render)

`report_ready` noul = **0.97 ≥ 0.95** → report stage (class gate `report
0.95 / confirm` → **operator signs** — the report gate is confirm-not-auto
by construction). Renderer walks the graph:

```cypher
MATCH (f:Finding {engagement_id:'acme-lab', status:'validated'})
OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(e:Evidence)
RETURN f, e ORDER BY (0.7*f.severity + 0.3*f.bounty) DESC;   -- composite: code, not Jev
```

Rendered `reports/report.md` — findings ordered by priority; in this
engagement VF-011 leads (severity 3, bounty 3 → priority 3.0, ahead of
VF-002 enumeration at severity 2 / bounty 1 → 1.7 and VF-001 bundle key).
Closing writes `:Engagement{status:'closed', closed_at:…}`; `tdb.commit`
already ran; the Memgraph DB stays up for `ycb doctor` / audit.

## What you can verify in this repo

| thing | where |
|---|---|
| the two gate layers and 0.90/0.95 values | `config/decision-catalog.md` §G0/G1 + `schema/storage-layout.md` `engagement.toon` |
| the exact tool names invoked (`http_repeater`, `browser_agent_inspect`, …) | `orchestrator/loop.md` §3 table (checked against `hexstrike_mcp.py`) |
| the E/F/VF/AC ids and `SUPPORTED_BY` invariants | `schema/memgraph/engagement-graph.cypher` (node block + invariant checks) |
| the priors/commit text formats | `schema/tencentdb/memory-interface.md` |
| the skill `s-014` shape (trigger boundary + validation rule) | `memory-interface.md` recall example |

Nothing in this walkthrough is a new mechanism: intake (TOON + cypher seed),
recall (TD interface), decide (catalog), gate (loop §1), act (loop §3 +
closed-set params), store (vector/text indexes from the cypher file), learn
(commit), report (render from graph). If it reads plausible from those files
alone, the plan is self-consistent; if any step above needs a file not in
the repo, that's a gap in the plan, not in the example.