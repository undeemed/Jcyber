"""HexStrike hands adapter. Drives HexStrike's REST server (default
http://127.0.0.1:8888, verified against hexstrike_mcp.py on master): each tool
is a POST to /api/tools/<endpoint>, health at /health. Never touches the
/api/intelligence/* or ai_*/bugbounty_* surface (AGENTS.md invariant #7). The
MCP-tool-name -> endpoint-slug mapping (e.g. nmap_scan -> nmap, http_repeater
-> http-framework) is the verified _TOOL_ENDPOINT table below."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

import httpx

from jcyber.types import JSON

# MCP tool name -> REST endpoint slug for /api/tools/<slug>, verified against
# hexstrike_server.py @app.route declarations (HexStrike v6, 2026-09-19).
# Every tool jcyber exposes via MCP must have an entry here.
_TOOL_ENDPOINT: dict[str, str] = {
    # recon — passive
    "subfinder_scan": "subfinder",
    "amass_scan": "amass",
    "gau_discovery": "gau",
    "waybackurls_discovery": "waybackurls",
    "paramspider_discovery": "paramspider",
    "httpx_probe": "httpx",
    "wafw00f_scan": "wafw00f",
    # recon — active
    "nmap_scan": "nmap",
    "rustscan_fast_scan": "rustscan",
    "masscan_high_speed": "masscan",
    "nikto_scan": "nikto",
    "katana_crawl": "katana",
    "hakrawler_crawl": "hakrawler",
    "gobuster_scan": "gobuster",
    "dirb_scan": "dirb",
    "ffuf_scan": "ffuf",
    "feroxbuster_scan": "feroxbuster",
    "http_framework_test": "http-framework",
    # probing
    "nuclei_scan": "nuclei",
    "sqlmap_scan": "sqlmap",
    "wpscan_analyze": "wpscan",
    "dalfox_xss_scan": "dalfox",
    "xsser_scan": "xsser",
    "jaeles_vulnerability_scan": "jaeles",
    "jwt_analyzer": "jwt_analyzer",
    "api_fuzzer": "api_fuzzer",
    "graphql_scanner": "graphql_scanner",
    "comprehensive_api_audit": "comprehensive_api_audit",  # exact match
    "arjun_scan": "arjun",
    "qsreplace": "qsreplace",
    "http_repeater": "http-framework",
    "browser_agent_inspect": "browser-agent",
    "netexec_scan": "netexec",
    "smbmap_scan": "smbmap",
    "enum4linux_scan": "enum4linux",
    # fuzzing
    "wfuzz_scan": "wfuzz",
    # exploit
    "metasploit_run": "metasploit",
    "pwntools_exploit": "pwntools",
    "hydra_attack": "hydra",
    "hashcat_crack": "hashcat",
    "john_crack": "john",
    "responder_credential_harvest": "responder",
}


def _extract(text: str) -> str:
    """HexStrike wraps tool output in a JSON envelope ({stdout, stderr,
    return_code, ...}); surface stdout so evidence summaries carry the tool
    result, not the envelope. Non-JSON responses pass through unchanged."""
    try:
        obj: object = json.loads(text)
    except ValueError:
        return text
    if isinstance(obj, dict):
        out = cast("dict[str, object]", obj).get("stdout")
        if isinstance(out, str) and out.strip():
            return out.strip()
    return text


class HexStrikeHands:
    def __init__(self, client: httpx.Client, path_template: str = "/api/tools/{tool}") -> None:
        self._client = client
        self._path = path_template

    @classmethod
    def connect(
        cls, base_url: str = "http://127.0.0.1:8888", timeout: float = 300.0
    ) -> HexStrikeHands:
        return cls(httpx.Client(base_url=base_url, timeout=timeout))

    def close(self) -> None:
        self._client.close()

    def call(self, tool: str, params: Mapping[str, JSON]) -> str:
        slug = _TOOL_ENDPOINT.get(tool, tool)
        try:
            resp = self._client.post(self._path.format(tool=slug), json=dict(params))
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return f"[tool_error] {tool}: HTTP {e.response.status_code}"
        except httpx.HTTPError as e:
            return f"[tool_error] {tool}: {type(e).__name__}: {e}"
        return _extract(resp.text)
