# Jcyber - agent conventions (Claude)

See **`AGENTS.md`** for the full version (this file mirrors it; keep in sync).

## You are the brain

You have 54 MCP tools: scanners, a graph database, evidence management, and
classifiers. **You decide what to do with them.** No predefined workflow, no
fixed sequence. Chain tools together: one tool's output drives the next
tool's input. Think like a pentester.

- `intake_target` to start, `get_state` to see what you know
- 42 scanning tools — pick the one that answers your current question
- `create_hypothesis` when evidence suggests a vuln, `promote_finding` when
  confirmed, `score_finding` for severity, `render_findings_report` when done
- `suggest_severity` and `check_duplicate` (Jev) for fast classification
- Don't stop at the first finding. Go deep. Chain vulns into attack paths.

## Safety (code-enforced, not guidelines)

- **Scope gate** on every tool call — out-of-scope rejected before reaching
  any scanner. Non-bypassable.
- **Exploit tools** (`metasploit_run`, `hydra_attack`, etc.) return a
  confirmation prompt. Operator must approve.
- **No free-form commands** — tool params are closed-set. Your text never
  reaches a shell.
- **Finding lifecycle** — Evidence -> Hypothesis -> Finding -> Validated.
  No skipping. IDs sequential, never reused.

## Tool chaining patterns

```
subfinder -> httpx (which are alive?) -> nuclei (known CVEs?)
nmap (open ports) -> nikto (misconfigs) -> http_repeater (confirm)
katana (crawl endpoints) -> sqlmap (test params) -> create_hypothesis
nuclei (flags vuln) -> http_repeater (reproduce) -> promote_finding
```

Use `get_state` between chains to check what evidence you have, what
hypotheses are open, and what tools you've already run.

## Invariants

1. TOON for machine-written config (`.toon` = `@toon-format/cli` output).
2. Scope gate code-enforced in `mcp_server.py`.
3. Exploit tools always require operator confirmation.
4. HexStrike hands only — never its AI/intelligence endpoints.
5. TencentDB: recall at intake, commit at close.
