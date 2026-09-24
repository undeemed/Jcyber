"""HexStrike hands adapter. Drives HexStrike's REST server (default
http://127.0.0.1:8899, verified against hexstrike_mcp.py on master): each tool
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

# Per-tool timeout overrides (seconds). Tools not listed use the client
# default (300s). Recon behind CDN/WAF needs shorter timeouts; exploit
# tools need longer ones.
_TOOL_TIMEOUT: dict[str, float] = {
    # recon - passive (fast, external APIs)
    "subfinder_scan": 120,
    "amass_scan": 180,
    "gau_discovery": 60,
    "waybackurls_discovery": 60,
    "paramspider_discovery": 60,
    "httpx_probe": 120,
    "wafw00f_scan": 30,
    # recon - active (may hit CDN/firewall)
    "nmap_scan": 180,
    "rustscan_fast_scan": 60,
    "masscan_high_speed": 120,
    "nikto_scan": 180,
    "http_framework_test": 30,
    # crawling (can run long on big sites)
    "katana_crawl": 180,
    "hakrawler_crawl": 120,
    # brute-force (variable)
    "gobuster_scan": 180,
    "dirb_scan": 180,
    "ffuf_scan": 180,
    "feroxbuster_scan": 180,
    # probing (moderate)
    "nuclei_scan": 300,
    "wpscan_analyze": 120,
    "arjun_scan": 120,
    # quick checks
    "jwt_analyzer": 30,
    "qsreplace": 15,
    "http_repeater": 30,
}


# Common HTML markers that indicate we got a proxy/SPA page instead of
# actual tool output.
_HTML_MARKERS = ("<!doctype", "<html", "<!DOCTYPE")

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

# HexStrike endpoints use different primary-param names. jcyber always sends
# "target"; this table remaps it to the name each endpoint actually reads.
# Tools not listed here accept "target" natively.
_TARGET_PARAM: dict[str, str] = {
    # domain-based
    "subfinder_scan": "domain",
    "amass_scan": "domain",
    "gau_discovery": "domain",
    "waybackurls_discovery": "domain",
    "paramspider_discovery": "domain",
    # url-based
    "gobuster_scan": "url",
    "dirb_scan": "url",
    "sqlmap_scan": "url",
    "wpscan_analyze": "url",
    "ffuf_scan": "url",
    "feroxbuster_scan": "url",
    "xsser_scan": "url",
    "wfuzz_scan": "url",
    "katana_crawl": "url",
    "arjun_scan": "url",
    "jaeles_vulnerability_scan": "url",
    "dalfox_xss_scan": "url",
}

# httpx endpoint builds `httpx -l {target}` treating target as a file path.
# Workaround: pipe target via additional_args with -u flag instead.
_HTTPX_TOOL = "httpx_probe"


def _extract(text: str) -> str:
    """HexStrike wraps tool output in a JSON envelope ({stdout, stderr,
    return_code, ...}); surface stdout so evidence summaries carry the tool
    result, not the envelope. Non-JSON responses pass through unchanged."""
    try:
        obj: object = json.loads(text)
    except ValueError:
        return text
    if isinstance(obj, dict):
        d = cast("dict[str, object]", obj)
        # Surface error from HexStrike envelope
        if d.get("error"):
            return f"[tool_error] {d['error']}"
        out = d.get("stdout")
        if isinstance(out, str) and out.strip():
            return out.strip()
    return text


def _looks_like_html(text: str) -> bool:
    """True if text starts with an HTML doctype or tag -- proxy/SPA garbage."""
    stripped = text.lstrip()[:20]
    return any(stripped.startswith(m) for m in _HTML_MARKERS)


class HexStrikeHands:
    def __init__(
        self,
        client: httpx.Client,
        path_template: str = "/api/tools/{tool}",
        default_timeout: float = 300.0,
    ) -> None:
        self._client = client
        self._path = path_template
        self._default_timeout = default_timeout
        self._available_tools: frozenset[str] | None = None

    @classmethod
    def connect(
        cls, base_url: str = "http://127.0.0.1:8899", timeout: float = 300.0
    ) -> HexStrikeHands:
        return cls(httpx.Client(base_url=base_url, timeout=timeout), default_timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def ping(self) -> None:
        """Hit GET /health -- raises on connection failure or non-2xx."""
        self._client.get("/health").raise_for_status()

    def fetch_available_tools(self) -> frozenset[str]:
        """Query /health and return the set of tools HexStrike reports as
        installed/available.  Caches the result for the session lifetime."""
        if self._available_tools is not None:
            return self._available_tools
        try:
            resp = self._client.get("/health", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            available: set[str] = set()
            # /health returns {categories: {name: {tools: {name: {installed: bool}}}}}
            cats = data.get("categories", {})
            if isinstance(cats, dict):
                for cat in cats.values():
                    tools = cat.get("tools", {}) if isinstance(cat, dict) else {}
                    if isinstance(tools, dict):
                        for tname, tinfo in tools.items():
                            if isinstance(tinfo, dict) and tinfo.get("installed"):
                                available.add(tname)
            self._available_tools = frozenset(available)
        except Exception:
            # /health unavailable -- assume all tools available
            self._available_tools = frozenset()
        return self._available_tools

    def is_tool_available(self, mcp_name: str) -> bool | None:
        """Check if the underlying binary for an MCP tool is installed in
        HexStrike.  Returns None if availability data is unavailable."""
        avail = self.fetch_available_tools()
        if not avail:
            return None  # no data
        slug = _TOOL_ENDPOINT.get(mcp_name, mcp_name)
        return slug in avail

    def call(self, tool: str, params: Mapping[str, JSON]) -> str:
        slug = _TOOL_ENDPOINT.get(tool, tool)
        p = dict(params)

        # Remap "target" to the param name each HexStrike endpoint expects
        if "target" in p:
            rename = _TARGET_PARAM.get(tool)
            if rename:
                p[rename] = p.pop("target")
            elif tool == _HTTPX_TOOL:
                target = p["target"]
                p["target"] = "/dev/null"
                existing = str(p.get("additional_args", ""))
                p["additional_args"] = f"-u {target} {existing}".strip()

        timeout = _TOOL_TIMEOUT.get(tool, self._default_timeout)

        try:
            resp = self._client.post(self._path.format(tool=slug), json=p, timeout=timeout)
            resp.raise_for_status()
        except httpx.TimeoutException:
            return f"[tool_error] {tool}: timed out after {timeout}s"
        except httpx.HTTPStatusError as e:
            return f"[tool_error] {tool}: HTTP {e.response.status_code}"
        except httpx.HTTPError as e:
            return f"[tool_error] {tool}: {type(e).__name__}: {e}"

        # Detect proxy/SPA garbage BEFORE extraction.  The Caido port-collision
        # signature is raw HTML as the HTTP body (not valid JSON).  Tools like
        # browser_agent_inspect and http_repeater legitimately return HTML
        # inside the JSON envelope's "stdout" field — that's fine.
        if _looks_like_html(resp.text):
            return (
                f"[tool_error] {tool}: response is HTML, not tool output. "
                "HexStrike may be routing through a proxy that intercepted "
                "the request. Check HEXSTRIKE_URL and Caido port assignments."
            )

        return _extract(resp.text)
