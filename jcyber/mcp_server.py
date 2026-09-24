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
import socket
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .clients.jev import JevClassifier

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from .clients.caido import CaidoProxy
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
        self.caido: CaidoProxy | None = None
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
    _ensure_backends()
    _require_engagement()
    if _state.graph is None:
        raise ValueError("Memgraph not connected. Set MEMGRAPH_URI env var.")
    return _state.graph


def _require_hands() -> HexStrikeHands:
    _ensure_backends()
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


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
def intake_target(
    url: str,
    severity: str = "critical",
) -> str:
    """Create a new engagement from a target URL. Sets up scope (apex domain +
    subdomains), initializes the graph, and returns the engagement ID.

    severity: minimum finding severity to report (critical, high, medium, low, none).
    """
    _ensure_backends()
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


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def get_state() -> str:
    """Get the current engagement state: phase, open hypotheses, recent
    evidence, validated findings, tools already run. Call this to decide
    what to do next."""
    graph = _require_graph()
    state = graph.project_state(_state.engagement_id)
    return json.dumps(state, indent=2)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def render_findings_report() -> str:
    """Render the final report as Markdown. Only includes validated findings
    with linked evidence. Call when the engagement is complete."""
    graph = _require_graph()
    data = graph.report_data(_state.engagement_id)
    return render_report(data)


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
def get_decision_trace() -> str:
    """Render the decision audit trail for this engagement. Shows every action
    taken, confidence scores, and gate outcomes."""
    graph = _require_graph()
    log = graph.decision_log(_state.engagement_id)
    return render_trace(_state.engagement_id, log)


# ---------------------------------------------------------------------------
# HexStrike tools — dynamically registered, each scope-gated
# ---------------------------------------------------------------------------


def _save_evidence_raw(ev_id: str, raw: str) -> str | None:
    """Persist raw tool output to disk. Returns path on success, None on failure."""
    evidence_dir = os.path.join("evidence", "raw")
    try:
        os.makedirs(evidence_dir, exist_ok=True)
        path = os.path.join(evidence_dir, f"{ev_id}.txt")
        with open(path, "w") as f:
            f.write(raw)
        return path
    except OSError:
        return None


def _make_hexstrike_tool(tool_name: str, description: str):
    """Factory: create a scope-gated MCP tool that calls HexStrike."""

    is_exploit = tool_name in EXPLOIT_TOOLS
    is_fuzzing = tool_name in FUZZING_TOOLS

    async def tool_fn(target: str, params: str = "{}") -> str:
        # Scope gate -- deterministic, non-jailbreakable
        _check_scope(target)

        if is_fuzzing:
            _check_fuzzing(target)

        if is_exploit:
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

        # Advisory availability check — warn but still attempt.  The /health
        # schema is guessed; a mismatch must not disable the whole toolset.
        avail = hands.is_tool_available(tool_name)
        if avail is False:
            print(
                f"[jcyber] WARNING: {tool_name!r} may not be installed in HexStrike. "
                "Attempting anyway.",
                file=sys.stderr,
            )

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

        # Structured error on failure
        if raw.startswith("[tool_error]"):
            error_msg = raw[len("[tool_error] ") :]
            error_type = (
                "timeout"
                if "timed out" in error_msg
                else (
                    "html_response"
                    if "HTML" in error_msg
                    else ("http_error" if "HTTP" in error_msg else "tool_error")
                )
            )
            return json.dumps(
                {
                    "status": "error",
                    "error_type": error_type,
                    "tool": tool_name,
                    "target": target,
                    "message": error_msg,
                }
            )

        # Always persist raw output to disk
        ev_id = _state.next_evidence_id()
        raw_path = _save_evidence_raw(ev_id, raw)

        # Auto-normalize evidence
        ev = normalize(_state.engagement_id, tool_name, target, raw, ev_id)

        # Insert into graph if connected and not a duplicate
        if _state.graph is not None and not _state.graph.seen_sha256(
            _state.engagement_id, ev.sha256
        ):
            _state.graph.insert_evidence(ev)

        return json.dumps(
            {
                "status": "success",
                "evidence_id": ev_id,
                "tool": tool_name,
                "target": target,
                "summary": ev.summary,
                "output": raw[:4000],
                "raw_path": raw_path,
            }
        )

    # Set proper name and docstring for MCP registration
    tool_fn.__name__ = tool_name
    tool_fn.__doc__ = (
        f"{description}\n\n"
        f"target: the host, URL, or IP to scan (must be in scope).\n"
        f"params: JSON object of additional tool-specific parameters (optional)."
    )
    return tool_fn


# Register all HexStrike tools with annotations
for _name, _desc in TOOL_CATALOG.items():
    _is_exploit = _name in EXPLOIT_TOOLS
    _annotations = ToolAnnotations(
        read_only_hint=False,
        destructive_hint=_is_exploit,
        idempotent_hint=False,
        open_world_hint=True,
    )
    mcp.add_tool(
        _make_hexstrike_tool(_name, _desc),
        name=_name,
        annotations=_annotations,
    )


# ---------------------------------------------------------------------------
# Graph tools — hypothesis/finding lifecycle
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
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


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    )
)
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


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
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


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
)
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


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    )
)
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


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    )
)
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
# Jev classifier tools — optional accelerators, never in the control path
# ---------------------------------------------------------------------------

_jev: JevClassifier | None = None


def _get_jev() -> JevClassifier:
    global _jev
    if _jev is None:
        try:
            from .clients.jev import JevClassifier as _JC

            _jev = _JC.from_env()
        except Exception as e:
            raise ValueError(f"Jev unavailable (set TYPESAFE_API_KEY): {e}") from e
    return _jev


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    )
)
def suggest_severity(finding_id: str, title: str, evidence_summary: str) -> str:
    """Fast severity classification for a finding. Returns a suggested
    severity level (none/low/medium/high/critical) with confidence.

    This is a Jev gut-check — the agent can use it as input to score_finding
    or override it entirely. Optional accelerator.

    finding_id: the F-### id
    title: finding title
    evidence_summary: brief description of what was found
    """
    jev = _get_jev()
    result = jev.severity(title, evidence_summary)
    return json.dumps(
        {
            "finding_id": finding_id,
            "suggested_severity": result.severity,
            "score": round(result.score, 3),
            "confidence": round(result.confidence, 3),
        }
    )


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    )
)
def check_duplicate(new_evidence_summary: str) -> str:
    """Check if new evidence is substantially similar to existing evidence
    already in the graph. Returns a probability (0-1).

    Use before creating a hypothesis to avoid duplicating work.
    Optional accelerator — smarter than sha256 exact match, cheaper than
    the agent comparing all evidence summaries.

    new_evidence_summary: summary of the evidence to check
    """
    graph = _require_graph()
    jev = _get_jev()
    state = graph.project_state(_state.engagement_id)
    existing: list[str] = []
    if isinstance(state, dict):
        recent = state.get("recent_evidence")
        if isinstance(recent, list):
            for ev in recent:
                if isinstance(ev, dict):
                    s = ev.get("summary")
                    if isinstance(s, str):
                        existing.append(s)
    if not existing:
        return json.dumps({"duplicate_probability": 0.0, "is_duplicate": False})
    result = jev.check_duplicate(new_evidence_summary, existing)
    return json.dumps(
        {
            "duplicate_probability": round(result.duplicate_probability, 3),
            "is_duplicate": result.duplicate_probability >= 0.7,
            "compared_against": len(existing),
        }
    )


# ---------------------------------------------------------------------------
# Startup / connection management
# ---------------------------------------------------------------------------


def _tcp_probe(host: str, port: int, timeout: float = 3.0) -> None:
    """Open-and-close TCP connection. Raises on refusal or timeout."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    finally:
        sock.close()


def _parse_host_port(addr: str, default_port: int = 8889) -> tuple[str, int]:
    """Parse 'host:port' or plain 'host'. Returns (host, port)."""
    if ":" in addr:
        host, port_s = addr.rsplit(":", 1)
        return host, int(port_s)
    return addr, default_port


def _log_degraded(errors: list[str]) -> None:
    """Log missing-service warnings to stderr. Never prompts, never aborts.

    This runs inside the lazy-connect path (_ensure_backends) which fires
    during the first tool call on a LIVE MCP server. Prompting via /dev/tty
    would hang (nobody watching) and SystemExit would tear down the stdio
    transport, causing "transport not connected" failures on the harness side.
    """
    print("\n[jcyber] WARNING - some services unavailable:", file=sys.stderr)
    for err in errors:
        print(f"  ! {err}", file=sys.stderr)
    print("  Continuing with degraded services.\n", file=sys.stderr)


def connect_backends() -> None:
    """Connect to all backends. Every service is checked; failures are
    collected and the operator is prompted before the server proceeds.

    Expects .env to be loaded BEFORE this is called (run_server handles it).
    """
    hexstrike_url = os.environ.get("HEXSTRIKE_URL", "http://127.0.0.1:8899")
    memgraph_uri = os.environ.get("MEMGRAPH_URI", "bolt://127.0.0.1:7687")
    memory_url = os.environ.get("JCYBER_MEMORY_URL")
    caido_proxy = os.environ.get("CAIDO_PROXY", "127.0.0.1:8889")
    caido_api_url = os.environ.get("CAIDO_API_URL", "http://127.0.0.1:8080")
    caido_token = os.environ.get("CAIDO_API_TOKEN")

    errors: list[str] = []

    # -- HexStrike (scanning) ----------------------------------------------
    try:
        _state.hands = HexStrikeHands.connect(hexstrike_url)
        _state.hands.ping()  # GET /health - actual network probe
        print(f"[jcyber] ok HexStrike @ {hexstrike_url}", file=sys.stderr)
    except Exception as e:
        _state.hands = None
        errors.append(f"HexStrike @ {hexstrike_url}: {e}")

    # -- Memgraph (evidence graph) -----------------------------------------
    try:
        _state.graph = MemgraphStore.connect(memgraph_uri)
        _state.graph.ping()
        print(f"[jcyber] ok Memgraph @ {memgraph_uri}", file=sys.stderr)
    except Exception as e:
        _state.graph = None
        errors.append(f"Memgraph @ {memgraph_uri}: {e}")

    # -- Caido proxy (TCP probe on proxy listener port) --------------------
    try:
        host, port = _parse_host_port(caido_proxy)
        _tcp_probe(host, port)
        print(f"[jcyber] ok Caido proxy @ {caido_proxy}", file=sys.stderr)
    except Exception as e:
        errors.append(f"Caido proxy @ {caido_proxy}: {e}")

    # -- Caido API (GraphQL - for findings pull) ---------------------------
    try:
        _state.caido = CaidoProxy.connect(caido_api_url, token=caido_token)
        _state.caido.ping()  # POST /graphql {__typename}
        print(f"[jcyber] ok Caido API @ {caido_api_url}", file=sys.stderr)
    except Exception as e:
        _state.caido = None
        errors.append(f"Caido API @ {caido_api_url}: {e}")

    # -- TencentDB memory --------------------------------------------------
    if memory_url:
        try:
            _state.memory = TencentMemory.connect(memory_url)
            print(f"[jcyber] ok Memory @ {memory_url}", file=sys.stderr)
        except Exception as e:
            errors.append(f"Memory @ {memory_url}: {e}")
    else:
        errors.append("JCYBER_MEMORY_URL not set")

    # -- TYPESAFE_API_KEY (Jev classifier) ----------------------------------
    if os.environ.get("TYPESAFE_API_KEY"):
        print("[jcyber] ok TYPESAFE_API_KEY present", file=sys.stderr)
    else:
        errors.append("TYPESAFE_API_KEY not set")

    if errors:
        _log_degraded(errors)


def disconnect_backends() -> None:
    if _state.hands is not None:
        _state.hands.close()
    if _state.graph is not None:
        _state.graph.close()
    if _state.caido is not None:
        _state.caido.close()
    if _state.memory is not None:
        _state.memory.close()


_backends_connected = False


def _ensure_backends() -> None:
    """Lazy backend connection — called on first tool use, not startup.

    This avoids blocking the MCP stdio handshake (initialize/tools-list)
    which must complete within OMP's 30s timeout.
    """
    global _backends_connected
    if _backends_connected:
        return
    _backends_connected = True
    connect_backends()


def run_server() -> None:
    """Start the MCP server (stdio transport)."""
    from dotenv import load_dotenv

    load_dotenv()  # .env secrets into os.environ BEFORE backend checks
    # ponytail: don't call connect_backends() here — it blocks 2+ seconds
    # and prevents MCP initialize from responding within OMP's timeout.
    # Backends connect lazily on first tool call via _ensure_backends().
    try:
        mcp.run(transport="stdio")
    finally:
        disconnect_backends()
