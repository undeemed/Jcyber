# Agent conventions - Jcyber

## You are the brain

Jcyber gives you 54 MCP tools: scanners, a graph database, evidence
management, and classifiers. **You decide what to do with them.** There is
no predefined workflow, no fixed sequence, no script to follow. You have
everything a pentester has — recon tools, vulnerability scanners, fuzzers,
exploit frameworks, a replay proxy, and a structured evidence graph — wired
together through one interface.

Your job: look at the target, figure out what's there, find what breaks,
prove it, and report it. Use whatever tools make sense. Chain them: nmap
finds a port, httpx fingerprints the service, nuclei checks for CVEs,
http_repeater confirms the exploit, sqlmap extracts data. One tool's output
is the next tool's input. Think like a pentester, not like a script.

The scope gate protects you — every tool call is checked against the
engagement scope before it runs. You can't accidentally scan out-of-scope
targets. Exploit tools ask the operator for confirmation. Beyond that,
you have full autonomy.

## What you have

**42 scanning tools** (scope-gated, via HexStrike):
- Recon: `subfinder_scan`, `nmap_scan`, `httpx_probe`, `katana_crawl`, `ffuf_scan`, `gobuster_scan`, ...
- Probing: `nuclei_scan`, `sqlmap_scan`, `dalfox_xss_scan`, `wpscan_analyze`, `jwt_analyzer`, `graphql_scanner`, ...
- Fuzzing: `ffuf_scan`, `wfuzz_scan`, `api_fuzzer`
- Verification: `http_repeater`, `browser_agent_inspect`
- Exploit: `metasploit_run`, `hydra_attack`, ... (operator confirmation required)

**10 management tools:**
- `intake_target` — start an engagement from a URL
- `get_state` — see what you know so far (evidence, hypotheses, findings)
- `create_hypothesis` — record a testable claim from evidence
- `promote_finding` — confirm a hypothesis into a finding
- `score_finding` — rate severity
- `retire_hypothesis` — mark a dead end
- `render_findings_report` — produce the final report
- `get_decision_trace` — audit trail of what happened
- `recall_lessons` / `commit_learnings` — cross-engagement memory

**2 Jev classifiers** (optional, 8.7x faster than reasoning it yourself):
- `suggest_severity` — fast severity classification
- `check_duplicate` — is this evidence a repeat of something you already have?

## How to think about it

**Follow the evidence.** Every scan produces evidence (E-###). Read it.
What does it tell you? What should you probe next? What hypothesis does
it support or contradict?

**Chain tools.** The output of one tool drives the input of the next:
- `subfinder_scan` finds subdomains -> `httpx_probe` checks which are alive
- `httpx_probe` shows nginx 1.19 -> `nuclei_scan` with nginx templates
- `nuclei_scan` flags a path traversal -> `http_repeater` confirms it
- `http_repeater` confirms -> `create_hypothesis` -> `promote_finding`
- `nmap_scan` finds port 3306 -> `netexec_scan` enumerates -> `sqlmap_scan` exploits
- `browser_agent_inspect` extracts JS -> find API keys, internal endpoints, hardcoded secrets
- `jwt_analyzer` decodes token -> forge claims -> `http_repeater` replays with tampered JWT

**Reverse engineer what you find.** When you get a binary, APK, JS bundle,
or compiled asset from the target, pull it apart: strings-dump it, trace API
calls, extract hardcoded endpoints and keys, find version strings. Feed
those back into your scanning tools. An internal API URL found in minified
JS is a new target for `nuclei_scan` and `sqlmap_scan`. A leaked key in a
mobile binary is a finding and an access vector.
**Hunt zero-days from known CVEs.** Look up published CVEs for the versions
you fingerprint. Don't just run `nuclei_scan` templates — read the CVE
details, understand the root cause, and look for the same bug class in
unpatched code paths. A past CVE in a framework tells you what the
developers get wrong — check if they made the same mistake elsewhere.
Chain a known CVE with target-specific config to find exploitable paths
the templates miss. Combine findings: a low-severity info disclosure that
leaks an internal path + a path traversal = file read = potential zero-day
chain no scanner would catch. The goal is not to re-find known CVEs — it's
to use them as a map to find what nobody has reported yet.

**Go deep, not wide.** Don't run every tool on every target. Pick the tool
that answers your current question. If nmap shows port 3306 open, that's
more interesting than running another subdomain scan.

**Use the graph.** `get_state` tells you what you know. What hypotheses are
open? What evidence is unexamined? What tools have you already run? Use
this to decide what to do next.

**Don't stop early.** If you found one vulnerability, there are probably
more. Check other endpoints, other parameters, other services. Chain
findings into attack paths. A low-severity info disclosure + a medium IDOR
might chain into a critical data breach.

## Safety constraints (code-enforced, not guidelines)

1. **Scope gate** — deterministic string matching on every MCP tool call.
   Out-of-scope targets are rejected before reaching any scanner. You
   cannot bypass this.

2. **Exploit confirmation** — `metasploit_run`, `hydra_attack`,
   `hashcat_crack`, `john_crack`, `pwntools_exploit`,
   `responder_credential_harvest` return a confirmation prompt. The
   operator must approve.

3. **No free-form commands** — tool calls use closed-set params. Your
   reasoning text never reaches a shell, path, or URL.

4. **Finding lifecycle** — Evidence (E-###) -> Hypothesis (H-###) ->
   Finding (F-###) -> Validated Finding. No skipping. IDs sequential,
   never reused.

## Invariants (do not violate when editing this repo)

1. TOON everywhere machine-written config/state lives (`@toon-format/cli`
   encoder output).
2. Scope gate is code-enforced in `jcyber/mcp_server.py`, non-bypassable.
3. Exploit tools always require operator confirmation.
4. HexStrike is hands only — never invoke its AI/intelligence endpoints.
5. TencentDB: read at recall, written at commit, never mid-run.

## Repo layout

| Path | What |
|------|------|
| `jcyber/mcp_server.py` | MCP server, 54 tools |
| `jcyber/SKILL.md` | Pentesting methodology |
| `jcyber/clients/jev.py` | Jev classifiers (severity, duplicate) |
| `jcyber/scope.py` | Scope gate |
| `jcyber/clients/` | HexStrike, Memgraph, TencentDB, Caido adapters |
| `schema/` | Graph schema, TOON shapes, memory interface |
| `tests/` | pytest suite |
| `SETUP.md` | First-time setup guide |
