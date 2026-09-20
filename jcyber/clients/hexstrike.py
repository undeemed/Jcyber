"""HexStrike hands adapter. Drives HexStrike's REST server (default
http://127.0.0.1:8888, verified against hexstrike_mcp.py on master): each tool
is a POST to /api/tools/<endpoint>, health at /health. Never touches the
/api/intelligence/* or ai_*/bugbounty_* surface (AGENTS.md invariant #7). The
MCP-tool-name -> endpoint-slug mapping (e.g. nmap_scan -> nmap) is applied via
path_template at live wiring (P2)."""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from jcyber.types import JSON


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
        resp = self._client.post(self._path.format(tool=tool), json=dict(params))
        resp.raise_for_status()
        return resp.text
