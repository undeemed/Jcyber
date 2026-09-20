"""next_action class -> HexStrike tool + closed-set params. The tool names are
the exact MCP names from orchestrator/loop.md section 3 (verified against
hexstrike_mcp.py). Every param resolves from cfg/scope/graph state -- never
from Jev free text (AGENTS.md invariant #5)."""

from __future__ import annotations

from .config import Engagement
from .types import JSON, ActionClass, Scope, ToolCall

# First entry is the default; loop.md section 3 carries the full ordered list.
CLASS_TOOLS: dict[ActionClass, tuple[str, ...]] = {
    ActionClass.recon_passive: (
        "subfinder_scan",
        "amass_scan",
        "gau_discovery",
        "waybackurls_discovery",
        "paramspider_discovery",
        "httpx_probe",
        "wafw00f_scan",
    ),
    ActionClass.recon_active: (
        "nmap_scan",
        "rustscan_fast_scan",
        "masscan_high_speed",
        "httpx_probe",
        "nikto_scan",
        "katana_crawl",
        "hakrawler_crawl",
        "gobuster_scan",
        "dirb_scan",
        "ffuf_scan",
        "feroxbuster_scan",
        "http_framework_test",
    ),
    ActionClass.probing: (
        "nuclei_scan",
        "sqlmap_scan",
        "wpscan_analyze",
        "dalfox_xss_scan",
        "xsser_scan",
        "jaeles_vulnerability_scan",
        "jwt_analyzer",
        "api_fuzzer",
        "graphql_scanner",
        "comprehensive_api_audit",
        "arjun_scan",
        "qsreplace",
        "http_repeater",
        "browser_agent_inspect",
        "netexec_scan",
        "smbmap_scan",
        "enum4linux_scan",
    ),
    ActionClass.fuzzing: ("ffuf_scan", "wfuzz_scan", "api_fuzzer", "jaeles_vulnerability_scan"),
    ActionClass.verify: ("http_repeater", "browser_agent_inspect", "nuclei_scan"),
    ActionClass.exploit: (
        "metasploit_run",
        "pwntools_exploit",
        "netexec_scan",
        "hydra_attack",
        "hashcat_crack",
        "john_crack",
        "responder_credential_harvest",
    ),
}


def route(action: ActionClass, target: str, cfg: Engagement, scope: Scope) -> ToolCall | None:
    """Map a gated action to a closed-set HexStrike tool call. report (local
    renderer) and commit (terminal) return None. Params are the P1 closed-set
    baseline (target, Caido proxy, no_fuzzing_on); the MCP-name -> REST-slug
    mapping is verified in HexStrikeHands._TOOL_ENDPOINT. Per-tool param
    specialization lands at live wiring (P2)."""
    tools = CLASS_TOOLS.get(action)
    if not tools:
        return None
    params: dict[str, JSON] = {"target": target}
    # passive recon runs unproxied, straight to the target (PLAN section 3)
    if action is not ActionClass.recon_passive:
        params["proxy"] = cfg.caido_proxy
    if action is ActionClass.fuzzing:
        params["no_fuzzing_on"] = list(scope.no_fuzzing_on)
    return ToolCall(tool=tools[0], params=params)
