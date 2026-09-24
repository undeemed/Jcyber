# FAQ

**What is Jcyber?**
An MCP toolkit for agent-driven pentesting. The agent harness (Claude Code,
or any MCP-capable LLM) is the reasoning loop. Jcyber provides scope-gated
scanning tools, an evidence graph, a finding lifecycle, and long-term memory
through an MCP server with 54 tools.

**How does the agent drive a pentest?**
The agent connects to Jcyber's MCP server and calls tools: scanning tools to
find vulnerabilities, graph tools to create hypotheses and promote findings,
memory tools to recall prior lessons. The agent reads `SKILL.md` for the
pentesting methodology (the ladder: reach, understand, primitive, escalate,
chain).

**How is scope enforced?**
Deterministic string matching against `scope.toon`, enforced as a code
pre-hook on every MCP tool call (`jcyber/mcp_server.py`). Out-of-scope
targets are rejected before reaching any scanner. This is not
prompt-bypassable - it is a code check, not a model check.

**Does any LLM text reach a shell, path, or URL?**
No. HexStrike calls are (tool name, closed-set params): target from
`scope.toon`, attack surface from graph node ids, sets from config. The
agent's reasoning text only selects which tool to call and with what
target - the target is then scope-checked in code.

**What about exploit actions?**
Exploit tools (`metasploit_run`, `hydra_attack`, `hashcat_crack`, etc.)
return a `CONFIRMATION_REQUIRED` response instead of executing. The
operator must approve before any exploit runs.

**Why Caido, and why port 8889?**
Caido is the traffic substrate: every target-touching call flows through a
pinned local proxy (`127.0.0.1:8889`), so all wire traffic is logged and
passively plugin-checked (Autorize, Scanner). Port 8889 is one above
HexStrike's REST default `:8899`, so the pair stays adjacent and
collision-free.

**Is anything runnable today?**
Yes. The MCP server with 54 tools, scope gate, evidence graph, and finding
lifecycle. `python -m jcyber serve` starts it. Connect any MCP-capable agent.

**What backends are required?**
- HexStrike server on `:8899` (the scanning tools)
- Memgraph on `:7687` (the engagement graph)
- Caido on `:8889` (proxy) and `:8080` (API)
- `TYPESAFE_API_KEY` and `CAIDO_API_TOKEN` in `.env`
- Optionally: TencentDB memory-core (`JCYBER_MEMORY_URL`)

## Comparison to other pentest tools

| Dimension | Jcyber | Strix | XBOW | Caido (+ AI) | Classic tooling |
|-----------|--------|-------|------|--------------|-----------------|
| Decision layer | Agent harness (any LLM) | Built-in agent loop | Proprietary | Manual / copilot | Manual |
| Scope enforcement | Code pre-hook, deterministic | Config-based | Platform-scoped | Manual | Manual |
| Evidence tracking | Graph (Memgraph) | File-based | Platform | Project-based | Scattered |
| Finding lifecycle | Strict (E->H->F->VF) | Varies | Platform | Manual | Manual |
| Extensibility | Any MCP client | Plugin system | Closed | Plugin system | Scripts |
| Open source | MIT | Apache-2.0 | No | No (proxy is proprietary) | Varies |

## Legal note

Jcyber assumes **in-scope targets only**. The scope gate is load-bearing,
not decorative: deterministic string matching enforced in code as a pre-hook
on every MCP tool call. Out-of-scope targets are rejected before reaching
any scanner. Nothing in this repo grants permission to test any system.
Authorization is the operator's responsibility.
