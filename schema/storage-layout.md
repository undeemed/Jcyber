# Engagement storage layout

One directory per engagement under `$JCYBER_HOME` (default `./engagements`).
Prometheus's vault layout, adapted: the *structured* memory lives in Memgraph,
the *raw* memory lives here, the *durable* memory lives in TencentDB.

**Config and state on disk are TOON** ([toon-format/toon](https://github.com/toon-format/toon)).
TOON is a lossless, token-efficient encoding of the JSON data model. All
machine-written config/state files in this repo use `.toon`: they are produced
JSON→TOON by the encoder (never hand-written syntax), validated by length
declarations and field lists on read, and re-read natively by any LLM.

```
engagements/<slug>/
  scope.toon                # AUTHORITATIVE scope. Operator-owned. Never written
                            # by the framework. Mirrored to :Scope nodes.
  engagement.toon           # target, program, rules of engagement, rate
                            # limits, timebox, Jev model pin, gate thresholds.
                            # Created at intake; effectively immutable.
  evidence/
    raw/                    # immutable tool output, named <sha256>.<ext>
    screenshots/            # browser-agent captures, <E-id>-<seq>.png
    captures/               # HARs, PCAPs, whatever binary the probe spits out
  pocs/
    <F-id>.md               # reproducible PoC per finding (steps, request,
                            # response, account used, exact env)
  reports/
    report.md               # rendered from graph at report_ready gate
    findings/               # per-finding client-ready writeups
  learnings/                # DISTILLER OUTBOX (async → TencentDB)
    atoms.md                # new L1 atom candidates, one per line, with ids
    skills.md               # skill candidates (worked bypass → procedure)
    scenario.md             # L2 scenario update (phase, done, abandoned+why)
    status.json             # last distiller run, uncommitted count, errors
  state/
    snapshot.json           # last projected Jev state (debug/replay)
    decisions.jsonl         # Decision-node export (audit, human-browsable)
```

## What goes where (rule of thumb)

| Question | Answer |
|---|---|
| "Will this be bigger than ~100 kB, or binary, or sensitive?" | → `evidence/` (vault). Graph gets only the summary + sha256 + path. |
| "Does another part of the loop branch on this?" | → Memgraph node (it must be queryable + traversable). |
| "Will the next engagement (on a similar target) need this?" | → `learnings/` outbox → TencentDB (atom/skill/scenario). |
| "Is this a deliverable a human reads?" | → `reports/` or `pocs/`. |

## Scope file shape

The deterministic gate reads `scope.toon`. Plain, strict, no cleverness.
Shown here is the TOON encoding of the JSON shown next to it.

```toon
# scope.toon — exactly what @toon-format/cli emits for the JSON below
engagement: acme-lab
authorized:
  reference: BBprogram acme-lab scope 2026-09-19
in_scope[4]{kind,value,note}:
  host,acme-lab.example,""
  prefix,*.acme-lab.example,""
  path,acme-lab.example/api/,no /admin (see out)
  ip_range,203.0.113.0/24,""
out_of_scope[2]{kind,value,note}:
  host,staging.acme-lab.example,no active scanning
  path,acme-lab.example/pay/,"payment: Do Not Test"
constraints:
  rate_limit_rps: 5
  time_window: "08:00-20:00 UTC"
  no_fuzzing_on[2]: /checkout,/pay
  authorized_accounts[2]: jcyber-test1@acme-lab.example,jcyber-test2@acme-lab.example
```

```json
{
  "engagement": "acme-lab",
  "authorized": { "reference": "BBprogram acme-lab scope 2026-09-19" },
  "in_scope": [
    { "kind": "host",     "value": "acme-lab.example" },
    { "kind": "prefix",   "value": "*.acme-lab.example" },
    { "kind": "path",     "value": "acme-lab.example/api/", "note": "no /admin (see out)" },
    { "kind": "ip_range", "value": "203.0.113.0/24" }
  ],
  "out_of_scope": [
    { "kind": "host", "value": "staging.acme-lab.example", "note": "no active scanning" },
    { "kind": "path", "value": "acme-lab.example/pay/",    "note": "payment: Do Not Test" }
  ],
  "constraints": {
    "rate_limit_rps": 5,
    "time_window": "08:00-20:00 UTC",
    "no_fuzzing_on": ["/checkout", "/pay"],
    "authorized_accounts": ["jcyber-test1@acme-lab.example", "jcyber-test2@acme-lab.example"]
  }
}
```

Gate rule (deterministic layer): an action is **in-scope** iff its target
(host/port/path) matches at least one `in_scope` item AND matches no
`out_of_scope` item AND satisfies `constraints`. Out-of-scope always wins on
conflict. The Jev `scope_safe` noul is a *second* check on top — never a
substitute.

## Engagement config shape

`engagement.toon` (TOON):

```toon
# engagement.toon — exactly what @toon-format/cli emits for the JSON below
target: acme-lab.example
program: acme-lab bug bounty
jev:
  model: jev-latest
  state_budget_chars: 24000
gates[6:]{auto,else}:
  recon_passive: 0.8,queue
  recon_active: 0.85,queue
  probing: 0.9,confirm
  fuzzing: 0.95,confirm
  report: 0.95,confirm
  scope_model_floor: 0.9,queue
verdicts:
  promote: 0.8
  retire: 0.2
budget:
  wallclock_hours: 24
  jev_calls: 500
  tool_runs: 300
```

```json
{
  "target": "acme-lab.example",
  "program": "acme-lab bug bounty",
  "jev": { "model": "jev-latest", "state_budget_chars": 24000 },
  "gates": {
    "recon_passive":     { "auto": 0.80, "else": "queue" },
    "recon_active":      { "auto": 0.85, "else": "queue" },
    "probing":           { "auto": 0.90, "else": "confirm" },
    "fuzzing":           { "auto": 0.95, "else": "confirm" },
    "report":            { "auto": 0.95, "else": "confirm" },
    "scope_model_floor": { "auto": 0.90, "else": "queue" }
  },
  "verdicts": { "promote": 0.8, "retire": 0.2 },
  "budget": { "wallclock_hours": 24, "jev_calls": 500, "tool_runs": 300 }
}
```


(Per the open question D4 in PLAN.md, the `model` pin is set per engagement:
use a dated Jev version for reproducible runs.)

## Git policy

- Framework code: committed here.
- `engagements/`: **gitignored by default** (evidence is sensitive). An
  engagement *can* be committed if the operator says so — then `evidence/raw/`
  is always excluded. `scope.toon` + `learnings/` are the reviewable parts.