# TencentDB Agent Memory — interface

TencentDB plays one role in the chain: **long-term brain**. The contract
with the rest of Jcyber is deliberately small — two methods. Everything else
(L0→L3 distillation, symbolic short-term memory, heterogeneous DB/Markdown
storage, the Hub panel, ACLs) is *inside* the box and swappable, which is
what lets us start on the standalone backend (D1 (b): SQLite +
sqlite-vec) and migrate to the hosted TCB instance without touching the
orchestrator.

```
                 ┌────────────────────────────── memory-core ──────────────┐
intake ── recall ──▶ L3 persona      (team/agent level: program knowledge)  │
                   L2 scenario       (per-engagement working context)        │  distill
loop   ── none ──▶  (never in hot path)                                       │
close ── commit ──▶ L1 atoms          (fact, target-scoped)  ─────────────────┘
                   skill store      (procedure + trigger boundary + validation)
                 └──────────────────────────────────────────────────────┘
```

**Rule: read at recall, write at commit, never between.** No loop
iteration may issue a write or a blocking read against this interface.
Everything below is enforced by the orchestrator, not by the memory
backend.

## API

Both methods are synchronous from the loop's point of view (called once at
intake, once at close) and return plain text / accept plain text +
structured fields. The text forms below are exactly what crosses the
boundary.

### `recall(engagement) -> RecallResult`

Called **once**, at intake, before the first iteration.

```python
recall(engagement)  # engagement: slug + scope.toon (targets, program, accounts)
```

Returns a **capped text block** (≤ 2000 chars) injected into the
`priors` section of every Jev state for the life of the engagement:

```
priors (from long-term memory):
  [skill s-014] sequential-id IDOR probe
    trigger: endpoint with numeric id returns full record; second authorized account available
    procedure: 1 swap id 2 swap Accept 3 confirm on second account
    last validated: 2026-07-02 (acme-lab, VF-008)
  [skill s-021] subdomain takeover of dormant wildcard CNAMEs
    trigger: subdomain resolves to CNAME with 0x0/0x8 NXDOMAIN owner
    last validated: 2026-05-19
  [atom] acme-lab.example: vendor runs F5 BIG-IP (2025-11)
  [atom] acme-lab.example: /api/v1 legacy surface, sequential ids, unauthenticated GET
  [scenario] prior engagement acme-lab (2026-03, 3 weeks): phase active_probing,
    done: recon+auth bypasses, abandoned: /pay/ (out of scope), 2 findings reported
```

Selection inside the box (not our concern, but stated for migration
parity): L2 scenario keyed on the scope (same vendor / same program),
L1 atoms matching scope targets, the **skill loadout** bound to the "Jcyber"
agent. The skills list also seeds the `skill_pick` question (catalog
§G1) — its criterion strings *are* the trigger boundary + validation rule
fields, so the question prompt is assembled in code, not prose.

### `commit(engagement, outbox) -> CommitResult`

Called **once**, at close (or at an explicit `ycb learnings export`).
Input is the distiller's outbox files (see `schema/storage-layout.md` →
`learnings/`):

- `atoms.md` — new L1 atom candidates, one per line, each carrying its
  source evidence id:
  `acme-lab.example: /api/users/{id} is an IDOR read, auth check missing on GET (E-041)`
- `skills.md` — skill candidates: a procedure that *worked* (a bypass with
  a passing validation check), each with trigger boundary + validation rule
- `scenario.md` — the engagement's L2 scenario update: phase reached, what was
  done, what was abandoned and why
- `status.json` — last distiller run state

```python
commit(engagement, atoms=[...], skills=[...], scenario={...})
```

The box handles the heavy half: L0 conversation → L1 atom → L2 scenario →
L3 persona distillation, dedup / supersede against existing memory, and a
guaranteed top-layer→raw traceability link (each committed atom/skill
carries the engagement + evidence ids it was distilled from, so any
"priors" line can be traced back to `E-###` in that engagement's graph).
Returns per-item: `created | updated | superseded: <id> | rejected: <reason>` —
the rejection reasons are appended to `learnings/status.json`.

## Why the seam is this shape

- **Swappable backend.** Standalone (memory-core + SQLite + sqlite-vec) and
  hosted TCB both satisfy the two methods. The Hub panel / team ACLs are a
  later concern (PLAN D1) and do not change this file.
- **Cheap to fake in tests.** The orchestrator's P3 (reflex + hands) runs
  against a fixture `recall` (returns a canned priors block) and a recording
  `commit` (appends to a local file) — the whole loop testable with zero
  network dependency on the memory stack.
- **No hot-path exposure.** If TencentDB is slow, absent, or down at intake,
  `recall` fails open with an **explicit empty** (`priors: (long-term
  memory unavailable — this run starts cold)`) and the loop proceeds; no
  silent degradation. If `commit` fails at close, the outbox files stay on
  disk, `status.json` records the error, and `ycb learnings export` retries —
  nothing is lost, just deferred.
- **Write is a one-shot, not a stream.** Durable knowledge should be
  distilled *once* on closure (when the phase is settled and causes are
  known), not drip-fed mid-run: partial-phase facts are the source of
  mis-remembered state, and `status.json` gives us the retry primitive
  instead.