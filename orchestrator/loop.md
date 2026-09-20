# Control loop

Expanded spec for PLAN §5. One loop thread per engagement. **Cadence: one
iteration per tool-run** — never wall-clock. Each iteration: project state →
one Jev call (question fan-out) → gates → one tool run → normalize → record
decision. Fan-out keeps one iteration cheap: N parallel questions cost
~1× one question per TypeSafe's cookbook, against N separate calls.

## 1. Invariants

1. Exactly one `system_one` call per iteration. Questions come only from
   `config/decision-catalog.md` — no ad-hoc free-text questions in the loop.
2. Gates run in order and **all** must pass: deterministic scope →
   `scope_safe` noul → confidence-by-class. Any failure records a `:Decision`
   with `outcome ∈ blocked | confirm_parked` and stops *that* action.
3. One tool run per iteration. "The scan is big" is not a reason to batch
   runs; it is a reason to raise the timebox in `engagement.toon`.
4. Jev answer text is never concatenated into a command, path, or shell
   string. Answers index into closed sets (§3, §4).

## 2. Pseudocode

```python
def loop(slug):  # orchestrator process
    scope = toon.load(f"engagements/{slug}/scope.toon")  # authoritative
    cfg = toon.load(f"engagements/{slug}/engagement.toon")  # pin + gates + budget
    priors, skills = tdb.recall(slug, scope)  # memory-interface.md
    mg.seed(slug, scope)  # engagement-graph.cypher

    while eng_active(slug) and within_budget(cfg.budget):
        snap = mg.project(slug)  # the graph's "state projector"
        state = render_state(snap, priors, notes, budget_left(cfg), cap=cfg.jev.state_budget_chars)
        q = catalog.assemble(snap, skills)  # decision-catalog.md
        ans = jev.system_one(state, q, model=cfg.jev.model)
        cls, tool, target = resolve(ans)  # class table §3; `commit` handled below

        # gate 1 — deterministic scope (string match vs scope.toon).
        # No model. Never re-argued; a fail is a scope violation, full stop.
        if not in_scope(target, scope):
            record(ans, "blocked")
            return HALT(scope_violation)

        # gate 2 — modeled scope (catalog G0)
        if ans.scope_safe.noul < cfg.gates.scope_model_floor.auto:  # 0.90
            record(ans, "confirm_parked")
            park(ans)
            continue

        # gate 3 — exploit is NEVER auto (PLAN §4.4): confirm-park regardless
        # of confidence, even 0.95+. Dedicated branch, checked before the
        # class-threshold table.
        if cls == "exploit":
            record(ans, "confirm_parked")
            park(ans)
            continue

        # confidence by class. recon classes auto at a lower bar and queue
        # below it; probing/fuzzing/report are confirm-parked below their
        # class auto-threshold; verify below threshold just re-decides next
        # iteration (a re-POC is not an operator decision).
        thr = {
            "recon_passive": 0.80,
            "recon_active": 0.85,
            "probing": 0.90,
            "fuzzing": 0.95,
            "verify": 0.90,
            "report": 0.95,
        }
        if ans.next_action.confidence < thr[cls]:
            record(ans, "confirm_parked")
            if cls == "verify":  # nothing new to act on:
                continue  # re-decide next iteration
            park(ans)
            continue

        if cls == "commit":  # terminal: distill + close
            render_report(slug, forced=True)  # operator committed the loop
            tdb.commit(slug, distill(slug))
            return CLOSE

        record(ans, "auto")

        rate_gate(target, scope.constraints)  # rps + time window (pre-conditions)
        raw = hexstrike.call(tool, closed_params(tool, target, cfg, ans))
        e = normalize(slug, tool, target, raw)  # sha256 vault → E-### → embed → dedup
        apply_verdicts(slug, ans, e)  # h_*_supported: ≥0.80 promote, ≤0.20 retire
        if ans.report_ready.noul >= 0.95:  # else: confirm (operator signs)
            render_report(slug)
            tdb.commit(slug, distill(slug))
            return CLOSE
        distill_to_outbox(slug)  # async; tdb.commit later
```

Halt (in addition to budget exhaustion, catalog §Budgets): 3 consecutive gate
failures on distinct targets → `HALT` + diagnostic; `report_ready` under
threshold twice with unchanged state → `HALT` + diagnostic. Never silently
loop past a repeated failure.

## 3. `next_action` class → tool routing (HexStrike MCP + Caido)

Tool names below are **exact MCP tool names** from a cached copy of
`hexstrike_mcp.py` (HexStrike v6, `main`; 151 named `@mcp.tool` entries,
retrieved 2026-09-19; the three least-common names were re-confirmed against
that copy on re-check). Verify against the current release before P3:
one `grep` over the file re-derives the whole list.

| class | tools (preferred order) | params drawn from |
|---|---|---|
| recon_passive | `subfinder_scan`, `amass_scan`, `gau_discovery`, `waybackurls_discovery`, `paramspider_discovery`, `httpx_probe`, `wafw00f_scan` | domain: scope.toon `in_scope`; source flags: config |
| recon_active | `nmap_scan`, `rustscan_fast_scan`, `masscan_high_speed`, `httpx_probe`, `nikto_scan`, `katana_crawl`, `hakrawler_crawl`, `gobuster_scan`, `dirb_scan`, `ffuf_scan` (shallow, `match_codes` from config), `feroxbuster_scan`, `http_framework_test` | targets + rate window: scope.toon; wordlists: config |
| probing | `nuclei_scan`, `sqlmap_scan`, `wpscan_analyze`, `dalfox_xss_scan`, `xsser_scan`, `jaeles_vulnerability_scan`, `jwt_analyzer`, `api_fuzzer`, `graphql_scanner`, `comprehensive_api_audit`, `arjun_scan`, `qsreplace`, `http_repeater`, `browser_agent_inspect`, `netexec_scan`, `smbmap_scan`, `enum4linux_scan` | target: state (E-###/Endpoint ids); template/tag sets + accounts: config / scope.toon `authorized_accounts` |
| fuzzing | `ffuf_scan` (volume), `wfuzz_scan`, `api_fuzzer` (volume), `jaeles_vulnerability_scan` (full) | param surface: established in earlier iterations; payload sets: config |
| verify | `http_repeater`, `browser_agent_inspect`, `nuclei_scan` (single template, config-pinned) | exact request bytes from the E-### / PoC record |
| replay | Caido edit/replay via the Caido API (HTTPQL-filtered export from this engagement's project; exact call names confirmed at P3) | request bytes: established `E-###` / vault export (id); field mutations: `scope.toon` / config closed sets; never Jev text |
| exploit | `metasploit_run`, `pwntools_exploit`, `netexec_scan` (creds), `hydra_attack`, `hashcat_crack`, `john_crack`, `responder_credential_harvest` | module + target: config closed sets; credentials: operator-supplied only |
| report | (local renderer; the MCP `create_vulnerability_report` is **unused by design**) | graph render; priority = `0.7·severity + 0.3·bounty` computed in code |

**Never called — HexStrike's own AI layer:** all `bugbounty_*` workflows,
`ai_*` / `intelligent_*` / `*_workflow` tools, and REST `/api/intelligence/*`
endpoints. Its v6 "Intelligent Decision Engine" is source-verified
hard-coded heuristics (signature/effectiveness maps, no model), so it is a
duplicate of Jev's role, not a second opinion. The "reflex" role belongs to
Jev (PLAN §2); letting two decision layers argue about the next action is
the failure mode this architecture exists to prevent.

**Jev-side BYOK engine (opt-in, evidence-only):** when
`cfg.engine.enabled` is true and the catalog question `route_via_engine`
answers `yes` for an *already-gated* action, the orchestrator makes one
OpenAI-compatible call to `https://api.cerebras.ai/v1` (model from
`cfg.engine.model`; `cfg.engine.model_trivial` for low-reasoning variants;
key read at runtime from the operator env var `CEREBRAS_API_KEY`, never in
the repo or in any `.toon`). The prompt is assembled in code from state +
closed sets (invariant 5 still holds — the engine's text never reaches a
shell, a command string, a path, or a URL). Its response is auxiliary text
(payload suggestion, parameter-set variant over a closed set, or response
interpretation) that becomes `:Evidence` with `tool: 'engine/<model>'` —
it feeds the dedup/hypothesis gates like any tool output and changes
nothing about the already-chosen action or its tool. With
`engine.enabled: false` (default) the loop is engine-free.

**REST fallback (closed-set only):** v6 tools that exist in the server but
have no named MCP primitive (e.g. `testssl`, `whatweb`, `x8`, `angr`,
`volatility3`) go through `POST /api/command` on `:8888` as
`{"command": "<template>", "use_cache": false}` where `<template>` is a
config file string with slots filled exclusively from scope.toon, graph node
values, or config — never from raw Jev text. One slot = one closed value.

**Proxy routing (Caido):** every target-touching class carries its `proxy`
param from config (`caido.proxy`, default `127.0.0.1:8889`) so all outbound
wire traffic is logged and passively plugin-checked by Caido;
passive/OSSINT-recon classes are exempt by class. One fresh Caido project
per engagement, created at intake, with its allow-scope mirrored from
`scope.toon`. The two-layer scope gate and the per-class confidence gate are
unchanged; Caido plugin verdicts (Autorize, Scanner) are evidence only —
they enter as `:Evidence` (`tool: 'caido/…'`) and never decide.

## 4. Parameter discipline


`scope.toon` supplies targets and `constraints` (rps, time window,
`no_fuzzing_on`). The deterministic gate enforces `no_fuzzing_on` and the
time window *before* any call — the tool table is not a place to re-check
these.
- **Closed sets only.** Every slot in a tool call resolves from one of:
`scope.toon` (target, accounts), graph node values (an established
`E-###`/`Endpoint` id), or `config/` (wordlists, nuclei tag sets, nuclei
template lists, msf modules+options, `caido.proxy`, engine model pins).
`replay`-class calls additionally resolve the exported request id and every
field mutation from `scope.toon`/config — never from Jev text. Jev answers
select *which* tool and *which element of a closed set* — they never supply
the string. This is what "no free-form command construction" means at the
call site.
- `additional_args`-style free-arg params (present on most MCP tools) are
**disabled in config**: the router passes only whitelisted slots; a bare
`additional_args` default means a config bug, not a capability.
- Wordlists and template sets live in the HexStrike environment (or a
pinned local path in config), referenced by name — contents are never
inlined into the request, so the audit log stays small and diffable.
- Rate window is a *pre-condition* on the class, not a tool param: recon
classes run inside `time_window` at `rate_limit_rps`; outside the window
the router parks the action (no retry, no delay-ladder; it simply never was
an action).

## 5. Failure handling

| failure | behavior | recorded as |
|---|---|---|
| tool run non-zero / timeout | one retry with `use_cache: false`; second failure → evidence of the *failure* is stored (E-###, summary "tool X failed on target Y: class of error"), the H that spawned it gets that evidence attached (it may be falsified) | `:ToolRun{exit}` + E-### |
| identical output twice | sha256 dedup collapses; second run is not a new evidence, not a new iteration trigger | DUP_OF |
| Jev call error | retry once; second error → suspend at current state (resume is the L2 scenario's job), no invented action | `:Decision{outcome:halted}` |
| operator rejects a parked action | rejected action + reason stored on the `:Decision`; next iteration's state includes "operator rejected: <class> against <target>, reason" — Jev must not immediately re-propose it (loop tracks 3-iteration cooldown per (class,target)) | `:Decision` annotation |
| budget line hit mid-run | finish in-flight run, normalize, stop | `:Engagement{status:completed/handed_off}` |