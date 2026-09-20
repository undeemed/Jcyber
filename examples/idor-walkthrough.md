# Walkthrough - one IDOR finding, end to end

One finding traced through MCP tool calls against the example engagement.
Same artifact ids, same target as the plan.

**The finding in one line:** on `acme-lab.example/api/`, an unauthenticated
GET `/api/users/{id}` returns the full user profile for any sequential id,
giving bulk PII exposure (email, phone, password-hash-adjacent fields).

Engagement: `acme-lab`, scope items `acme-lab.example`,
`*.acme-lab.example`, `acme-lab.example/api/`, `203.0.113.0/24`.

## Step 0 - Intake

The agent (or operator) calls `intake_target`:

```
intake_target(url="https://acme-lab.example", severity="critical")
```

Returns:
```json
{
  "engagement_id": "acme-lab",
  "target": "acme-lab.example",
  "scope": {
    "in_scope": ["host:acme-lab.example", "prefix:*.acme-lab.example"],
    "out_of_scope": []
  }
}
```

The engagement directory is created with `scope.toon` and `engagement.toon`.
Memgraph is bootstrapped with the `:Engagement` node and `:Scope` nodes.

## Step 1 - Recon

The agent runs passive and active recon:

```
httpx_probe(target="acme-lab.example")
```

Evidence `E-001` is auto-created. Summary: `acme-lab.example [200] [nginx/1.25]`.

```
nmap_scan(target="acme-lab.example", params='{"ports": "80,443,3306"}')
```

Evidence `E-002`: `22/tcp open ssh | 80/tcp open http | 443/tcp open https`.

The agent checks state:
```
get_state()
```

Returns phase, recent evidence, tools run.

## Step 2 - Probe

The agent notices an API endpoint from the crawl and probes it:

```
nuclei_scan(target="acme-lab.example")
```

Evidence `E-003`: template matches for exposed API endpoints.

```
http_repeater(target="https://acme-lab.example/api/users/1")
```

Evidence `E-004`: full user profile JSON returned for user id 1.

## Step 3 - Hypothesis

The agent creates a hypothesis from the evidence:

```
create_hypothesis(
    text="GET /api/users/{id} returns full profile for any id - IDOR",
    evidence_id="E-004"
)
```

Returns `{"hypothesis_id": "H-001"}`.

## Step 4 - Verify

The agent verifies with a different user id:

```
http_repeater(target="https://acme-lab.example/api/users/4821")
```

Evidence `E-005`: full profile for user 4821, a user neither test account owns.

```
http_repeater(
    target="https://acme-lab.example/api/users/4821",
    params='{"headers": {"Authorization": ""}}'
)
```

Evidence `E-006`: same response without any auth header - unauthenticated access confirmed.

## Step 5 - Finding

The agent promotes the hypothesis and scores the finding:

```
promote_finding(hypothesis_id="H-001", title="Unauthenticated IDOR on /api/users/{id}")
```

Returns `{"finding_id": "F-001"}`.

```
score_finding(
    finding_id="F-001",
    severity="critical",
    justification="Unauthenticated access to any user profile via sequential ID. Bulk PII exposure: email, phone, password-adjacent fields. No rate limiting."
)
```

Finding `F-001` is now validated with severity `critical`.

## Step 6 - Report

The agent renders the final report:

```
render_findings_report()
```

Output:

```markdown
# Jcyber report: acme-lab

1 validated finding(s), by id:

## F-001 - Unauthenticated IDOR on /api/users/{id}
- severity: critical
- evidence (3):
  - E-004 [http_repeater] full user profile for id 1
  - E-005 [http_repeater] full user profile for id 4821
  - E-006 [http_repeater] unauthenticated access confirmed
```

## What you can verify in this repo

| What | Where |
|------|-------|
| Scope gate blocks out-of-scope targets | `jcyber/scope.py` + `jcyber/mcp_server.py` |
| Tool names match HexStrike | `jcyber/mcp_server.py` TOOL_CATALOG |
| Evidence normalization (sha256, summary) | `jcyber/normalize.py` |
| Graph schema (E/H/F nodes, relationships) | `schema/memgraph/engagement-graph.cypher` |
| Memory interface (recall/commit) | `schema/tencentdb/memory-interface.md` |
| Finding lifecycle | `jcyber/mcp_server.py` graph tools |

Nothing in this walkthrough is a new mechanism. Every step maps to an MCP
tool call in `mcp_server.py`. If it reads plausible from the code alone,
the architecture is self-consistent.
