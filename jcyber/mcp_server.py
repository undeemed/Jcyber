"""Jcyber MCP server — exposes pentesting tools to an agent harness.

The harness (Claude Code, or any MCP-capable agent) is the reasoning loop.
Jcyber provides scope-gated tools, graph state, memory, and engagement
management. Safety is enforced in code: the scope gate runs before every
HexStrike call, exploit actions require operator confirmation, and all
evidence is normalized into the engagement graph.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

from .clients.hexstrike import HexStrikeHands
from .clients.memgraph import MemgraphStore
from .clients.tencentdb import TencentMemory
from .clients.toon import CliToonCodec
from .config import Engagement
from .intake import default_engagement_json, intake_link
from .learn import distill
from .normalize import normalize
from .report import render as render_report
from .scope import in_scope, violates_no_fuzzing
from .trace import render as render_trace
from .types import Scope

# ---------------------------------------------------------------------------
# Tool catalog: every HexStrike tool the agent can call, with a description
# the agent sees when listing tools. Grouped by phase.
# ---------------------------------------------------------------------------

TOOL_CATALOG: dict[str, str] = {
    # recon — passive
    "subfinder_scan": "Passive subdomain enumeration via multiple sources",
    "amass_scan": "In-depth subdomain enumeration and mapping",
    "gau_discovery": "Fetch known URLs from AlienVault, Wayback, Common Crawl",
    "waybackurls_discovery": "Fetch URLs from the Wayback Machine archive",
    "paramspider_discovery": "Mine parameters from web archives for a domain",
    "httpx_probe": "HTTP probe: live hosts, status codes, tech fingerprint, titles",
    "wafw00f_scan": "Detect web application firewalls",
    # recon — active
    "nmap_scan": "Port scan and service/version detection (TCP/UDP)",
    "rustscan_fast_scan": "Fast port scanner (Rust-based), feeds results to nmap",
    "masscan_high_speed": "High-speed port scanner for large ranges",
    "nikto_scan": "Web server vulnerability scanner (CGI, misconfig, headers)",
    "katana_crawl": "Fast web crawler for endpoint and parameter discovery",
    "hakrawler_crawl": "Simple fast web crawler for link and endpoint discovery",
    "gobuster_scan": "Directory/file/DNS/vhost brute-force",
    "dirb_scan": "Web content scanner (directory brute-force)",
    "ffuf_scan": "Web fuzzer — directories, parameters, vhosts, custom positions",
    "feroxbuster_scan": "Recursive content discovery (Rust-based web fuzzer)",
    "http_framework_test": "HTTP method and framework detection",
    # probing
    "nuclei_scan": "Template-based vulnerability scanner (9000+ templates)",
    "sqlmap_scan": "SQL injection detection and exploitation",
    "wpscan_analyze": "WordPress vulnerability scanner",
    "dalfox_xss_scan": "XSS vulnerability scanner and parameter analysis",
    "xsser_scan": "Cross-site scripting detection framework",
    "jaeles_vulnerability_scan": "Customizable vulnerability scanner",
    "jwt_analyzer": "JWT token analysis (signature, claims, known weaknesses)",
    "api_fuzzer": "API endpoint fuzzing (REST, GraphQL)",
    "graphql_scanner": "GraphQL introspection, injection, and DoS testing",
    "comprehensive_api_audit": "Full API security audit (auth, IDOR, injection, rate-limit)",
    "arjun_scan": "HTTP parameter discovery",
    "qsreplace": "Query string parameter replacement for testing",
    "http_repeater": "Replay and modify HTTP requests (like Burp Repeater)",
    "browser_agent_inspect": "Browser-based inspection (JS-rendered content, DOM)",
    "netexec_scan": "Network service enumeration (SMB, LDAP, WinRM, etc.)",
    "smbmap_scan": "SMB share enumeration and access testing",
    "enum4linux_scan": "Windows/Samba enumeration (users, shares, policies)",
    # fuzzing
    "wfuzz_scan": "Web fuzzer for parameters, headers, and paths",
    # verify
    # (http_repeater, browser_agent_inspect, nuclei_scan already listed)
    # exploit (require operator confirmation)
    "metasploit_run": "Metasploit module execution (REQUIRES OPERATOR CONFIRMATION)",
    "pwntools_exploit": "Custom exploit via pwntools (REQUIRES OPERATOR CONFIRMATION)",
    "hydra_attack": "Network login brute-force (REQUIRES OPERATOR CONFIRMATION)",
    "hashcat_crack": "Password hash cracking (REQUIRES OPERATOR CONFIRMATION)",
    "john_crack": "John the Ripper hash cracking (REQUIRES OPERATOR CONFIRMATION)",
    "responder_credential_harvest": (
        "LLMNR/NBT-NS credential harvesting (REQUIRES OPERATOR CONFIRMATION)"
    ),
}

# Exploit tools — require explicit operator confirmation before execution
EXPLOIT_TOOLS = frozenset(
    {
        "metasploit_run",
        "pwntools_exploit",
        "hydra_attack",
        "hashcat_crack",
        "john_crack",
        "responder_credential_harvest",
    }
)

# Fuzzing tools — blocked on paths in no_fuzzing_on
FUZZING_TOOLS = frozenset({"ffuf_scan", "wfuzz_scan", "api_fuzzer", "jaeles_vulnerability_scan"})


# ---------------------------------------------------------------------------
# Server state — initialized at startup, shared across all tool calls
# ---------------------------------------------------------------------------


class ServerState:
    """Mutable runtime state for the MCP server. Initialized from env vars
    and engagement directory at startup."""

    def __init__(self) -> None:
        self.hands: HexStrikeHands | None = None
        self.graph: MemgraphStore | None = None
        self.memory: TencentMemory | None = None
        self.cfg: Engagement | None = None
        self.scope: Scope | None = None
        self.engagement_id: str = ""
        self._ev_seq: int = 0
        self._h_seq: int = 0
        self._f_seq: int = 0

    def next_evidence_id(self) -> str:
        self._ev_seq += 1
        return f"E-{self._ev_seq:03d}"

    def next_hypothesis_id(self) -> str:
        self._h_seq += 1
        return f"H-{self._h_seq:03d}"

    def next_finding_id(self) -> str:
        self._f_seq += 1
        return f"F-{self._f_seq:03d}"


_state = ServerState()


def get_server_state() -> ServerState:
    """Public accessor for the server state singleton."""
    return _state


def _require_engagement() -> None:
    if not _state.engagement_id:
        raise ValueError("No engagement loaded. Call intake_target first.")


def _require_graph() -> MemgraphStore:
    _require_engagement()
    if _state.graph is None:
        raise ValueError("Memgraph not connected. Set MEMGRAPH_URI env var.")
    return _state.graph


def _require_hands() -> HexStrikeHands:
    if _state.hands is None:
        raise ValueError("HexStrike not connected. Set HEXSTRIKE_URL env var.")
    return _state.hands


def _require_scope() -> Scope:
    if _state.scope is None:
        raise ValueError("No scope loaded. Call intake_target first.")
    return _state.scope


def _check_scope(target: str) -> None:
    """Deterministic scope gate — runs before every HexStrike call.
    String matching against scope.toon, no model, non-jailbreakable."""
    scope = _require_scope()
    if not in_scope(target, scope):
        raise ValueError(
            f"BLOCKED: target {target!r} is out of scope. "
            f"In-scope: {[i.value for i in scope.in_scope]}. "
            f"Out-of-scope: {[o.value for o in scope.out_of_scope]}."
        )


def _check_fuzzing(target: str) -> None:
    scope = _require_scope()
    if violates_no_fuzzing(target, scope):
        raise ValueError(
            f"BLOCKED: fuzzing on {target!r} violates no_fuzzing_on constraint. "
            f"Protected paths: {list(scope.no_fuzzing_on)}"
        )


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = MCPServer(
    "jcyber",
    instructions=(
        "Jcyber pentesting toolkit. Use intake_target to start an engagement, "
        "then use scanning/probing tools to find vulnerabilities. All targets "
        "are scope-checked before execution. Create hypotheses from evidence, "
        "promote to findings when confirmed. Use get_state to see engagement "
        "progress. Use render_report when done."
    ),
)


# ---------------------------------------------------------------------------
# Engagement management tools
# ---------------------------------------------------------------------------


@mcp.tool()
def intake_target(
    url: str,
    severity: str = "critical",
) -> str:
    """Create a new engagement from a target URL. Sets up scope (apex domain +
    subdomains), initializes the graph, and returns the engagement ID.

    severity: minimum finding severity to report (critical, high, medium, low, none).
    """
    result = intake_link(url, severity)
    _state.engagement_id = result.slug
    CliToonCodec()

    # Build scope
    from .config import scope_from_json

    _state.scope = scope_from_json(result.scope_json)

    # Build engagement config
    eng_json = default_engagement_json(result.host, result.slug)
    _state.cfg = Engagement.from_json(eng_json)

    # Bootstrap Memgraph if connected
    if _state.graph is not None:
        scope_items = []
        raw_scope = result.scope_json
        if isinstance(raw_scope, dict):
            in_s = raw_scope.get("in_scope")
            if isinstance(in_s, list):
                scope_items: list[dict[str, str]] = [
                    {"kind": str(i.get("kind", "host")), "value": str(i.get("value", ""))}
                    for i in in_s
                    if isinstance(i, dict)
                ]
        _state.graph.bootstrap_engagement(result.slug, result.host, scope_items)

    return json.dumps(
        {
            "engagement_id": result.slug,
            "target": result.host,
            "scope": {
                "in_scope": [f"{i.kind}:{i.value}" for i in _state.scope.in_scope],
                "out_of_scope": [f"{i.kind}:{i.value}" for i in _state.scope.out_of_scope],
            },
            "severity_focus": severity,
            "status": "active",
        },
        indent=2,
    )


@mcp.tool()
def get_state() -> str:
    """Get the current engagement state: phase, open hypotheses, recent
    evidence, validated findings, tools already run. Call this to decide
    what to do next."""
    graph = _require_graph()
    state = graph.project_state(_state.engagement_id)
    return json.dumps(state, indent=2)


@mcp.tool()
def render_findings_report() -> str:
    """Render the final report as Markdown. Only includes validated findings
    with linked evidence. Call when the engagement is complete."""
    graph = _require_graph()
    data = graph.report_data(_state.engagement_id)
    return render_report(data)


@mcp.tool()
def get_decision_trace() -> str:
    """Render the decision audit trail for this engagement. Shows every action
    taken, confidence scores, and gate outcomes."""
    graph = _require_graph()
    log = graph.decision_log(_state.engagement_id)
    return render_trace(_state.engagement_id, log)


# ---------------------------------------------------------------------------
# HexStrike tools — dynamically registered, each scope-gated
# ---------------------------------------------------------------------------


def _make_hexstrike_tool(tool_name: str, description: str):
    """Factory: create a scope-gated MCP tool that calls HexStrike."""

    is_exploit = tool_name in EXPLOIT_TOOLS
    is_fuzzing = tool_name in FUZZING_TOOLS

    async def tool_fn(target: str, params: str = "{}") -> str:
        # Scope gate — deterministic, non-jailbreakable
        _check_scope(target)

        if is_fuzzing:
            _check_fuzzing(target)

        if is_exploit:
            # ponytail: return a confirmation prompt, don't auto-execute
            return json.dumps(
                {
                    "status": "CONFIRMATION_REQUIRED",
                    "tool": tool_name,
                    "target": target,
                    "message": (
                        f"Exploit tool {tool_name!r} requires explicit operator confirmation. "
                        "This is a safety constraint that cannot be bypassed. "
                        "Ask the operator to confirm before proceeding."
                    ),
                }
            )

        hands = _require_hands()
        extra: dict[str, Any] = json.loads(params) if params and params != "{}" else {}
        call_params: dict[str, Any] = {"target": target, **extra}

        # Route through Caido proxy for active tools
        if _state.cfg and tool_name not in {
            "subfinder_scan",
            "amass_scan",
            "gau_discovery",
            "waybackurls_discovery",
            "paramspider_discovery",
        }:
            call_params.setdefault("proxy", _state.cfg.caido_proxy)

        raw = hands.call(tool_name, call_params)

        # Auto-normalize evidence into graph
        if _state.graph is not None and not raw.startswith("[tool_error]"):
            ev_id = _state.next_evidence_id()
            ev = normalize(_state.engagement_id, tool_name, target, raw, ev_id)
            if not _state.graph.seen_sha256(_state.engagement_id, ev.sha256):
                _state.graph.insert_evidence(ev)
            return json.dumps(
                {
                    "evidence_id": ev_id,
                    "tool": tool_name,
                    "target": target,
                    "summary": ev.summary,
                    "output": raw[:4000],  # cap for context window
                }
            )

        return raw

    # Set proper name and docstring for MCP registration
    tool_fn.__name__ = tool_name
    tool_fn.__doc__ = (
        f"{description}\n\n"
        f"target: the host, URL, or IP to scan (must be in scope).\n"
        f"params: JSON object of additional tool-specific parameters (optional)."
    )
    return tool_fn


# Register all HexStrike tools
for _name, _desc in TOOL_CATALOG.items():
    mcp.add_tool(_make_hexstrike_tool(_name, _desc), name=_name)


# ---------------------------------------------------------------------------
# Graph tools — hypothesis/finding lifecycle
# ---------------------------------------------------------------------------


@mcp.tool()
def create_hypothesis(
    text: str,
    evidence_id: str,
) -> str:
    """Create a hypothesis (H-###) from evidence. A hypothesis is a
    testable claim about a potential vulnerability. It must reference
    specific evidence.

    text: what the hypothesis claims (e.g. "SQL injection in /api/search via q parameter")
    evidence_id: the E-### id of supporting evidence
    """
    graph = _require_graph()
    hid = _state.next_hypothesis_id()
    graph.create_hypothesis(_state.engagement_id, hid, text, evidence_id)
    return json.dumps({"hypothesis_id": hid, "text": text, "evidence_id": evidence_id})


@mcp.tool()
def promote_finding(
    hypothesis_id: str,
    title: str,
) -> str:
    """Promote a confirmed hypothesis to a Finding (F-###). Only do this
    when you have strong evidence that the vulnerability is real and
    reproducible.

    hypothesis_id: the H-### id to promote
    title: descriptive title for the finding
    """
    graph = _require_graph()
    fid = _state.next_finding_id()
    graph.create_finding(_state.engagement_id, fid, title, hypothesis_id)
    # Mark hypothesis as promoted
    graph.apply_verdict(_state.engagement_id, hypothesis_id, "promote", 1.0)
    return json.dumps({"finding_id": fid, "title": title, "from_hypothesis": hypothesis_id})


@mcp.tool()
def score_finding(
    finding_id: str,
    severity: str,
    justification: str = "",
) -> str:
    """Set the severity score on a finding. Severity determines whether it
    appears in the final report (based on the engagement's severity_focus).

    finding_id: the F-### id
    severity: one of: none, low, medium, high, critical
    justification: why this severity (attack impact, exploitability)
    """
    graph = _require_graph()
    sev_map = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    sev_int = sev_map.get(severity.lower())
    if sev_int is None:
        raise ValueError(f"severity must be one of {list(sev_map)}")
    graph.score_finding(_state.engagement_id, finding_id, sev_int)
    return json.dumps(
        {
            "finding_id": finding_id,
            "severity": severity,
            "justification": justification,
            "status": "validated" if sev_int >= 3 else "provisional",
        }
    )


@mcp.tool()
def retire_hypothesis(hypothesis_id: str, reason: str = "") -> str:
    """Retire a hypothesis that turned out to be false or untestable.

    hypothesis_id: the H-### id to retire
    reason: why it was retired
    """
    graph = _require_graph()
    graph.apply_verdict(_state.engagement_id, hypothesis_id, "retire", 0.0)
    return json.dumps({"hypothesis_id": hypothesis_id, "status": "retired", "reason": reason})


# ---------------------------------------------------------------------------
# Memory tools
# ---------------------------------------------------------------------------


@mcp.tool()
def recall_lessons(scope_description: str = "") -> str:
    """Recall lessons from long-term memory (prior engagements on similar
    targets, known techniques for this tech stack). Call early in the
    engagement to benefit from prior experience.

    scope_description: what to recall for (e.g. "WordPress 6.x, PHP, MySQL")
    """
    if _state.memory is None:
        return json.dumps({"status": "no_memory", "message": "Long-term memory not configured."})
    _require_engagement()
    priors = _state.memory.recall(
        _state.engagement_id,
        {"description": scope_description, "target": _state.cfg.target if _state.cfg else ""},
    )
    return json.dumps(priors, indent=2) if priors else '{"lessons": []}'


@mcp.tool()
def commit_learnings() -> str:
    """Distill and commit learnings from this engagement to long-term memory.
    Call at the end of the engagement. Captures validated findings and
    retired hypotheses as durable knowledge."""
    if _state.memory is None:
        return json.dumps({"status": "no_memory", "message": "Long-term memory not configured."})
    graph = _require_graph()
    projection = graph.project_state(_state.engagement_id)
    atoms = distill(projection)
    _state.memory.commit(_state.engagement_id, atoms)
    return json.dumps({"status": "committed", "atoms": atoms}, indent=2)


# ---------------------------------------------------------------------------
# Startup / connection management
# ---------------------------------------------------------------------------


def connect_backends() -> None:
    """Connect to backends from environment variables. Called at server start."""
    hexstrike_url = os.environ.get("HEXSTRIKE_URL", "http://127.0.0.1:8888")
    memgraph_uri = os.environ.get("MEMGRAPH_URI", "bolt://127.0.0.1:7687")
    memory_url = os.environ.get("JCYBER_MEMORY_URL")

    try:
        _state.hands = HexStrikeHands.connect(hexstrike_url)
        print(f"[jcyber] HexStrike connected @ {hexstrike_url}", file=sys.stderr)
    except Exception as e:
        print(f"[jcyber] HexStrike unavailable @ {hexstrike_url}: {e}", file=sys.stderr)

    try:
        _state.graph = MemgraphStore.connect(memgraph_uri)
        _state.graph.ping()
        print(f"[jcyber] Memgraph connected @ {memgraph_uri}", file=sys.stderr)
    except Exception as e:
        print(f"[jcyber] Memgraph unavailable @ {memgraph_uri}: {e}", file=sys.stderr)
        _state.graph = None

    if memory_url:
        try:
            _state.memory = TencentMemory.connect(memory_url)
            print(f"[jcyber] Memory connected @ {memory_url}", file=sys.stderr)
        except Exception as e:
            print(f"[jcyber] Memory unavailable @ {memory_url}: {e}", file=sys.stderr)


def disconnect_backends() -> None:
    if _state.hands is not None:
        _state.hands.close()
    if _state.graph is not None:
        _state.graph.close()
    if _state.memory is not None:
        _state.memory.close()


def run_server() -> None:
    """Start the MCP server (stdio transport)."""
    connect_backends()
    try:
        mcp.run(transport="stdio")
    finally:
        disconnect_backends()
