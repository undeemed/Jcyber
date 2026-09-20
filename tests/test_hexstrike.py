"""HexStrike adapter maps MCP tool names to the verified REST endpoint slugs
(/api/tools/<slug>). http_repeater -> http-framework is the non-obvious one;
an unmapped name passes through unchanged (correct for tools whose MCP name
already equals their slug, e.g. api_fuzzer)."""

from __future__ import annotations

import httpx

from jcyber.clients.hexstrike import HexStrikeHands


def _hands_capturing(seen: list[str]) -> HexStrikeHands:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, text="ok")

    client = httpx.Client(base_url="http://127.0.0.1:8888", transport=httpx.MockTransport(handler))
    return HexStrikeHands(client)


def test_mcp_name_maps_to_rest_slug() -> None:
    seen: list[str] = []
    hands = _hands_capturing(seen)
    hands.call("nmap_scan", {"target": "x"})
    hands.call("http_repeater", {"target": "x"})
    hands.call("ffuf_scan", {"target": "x"})
    assert seen == ["/api/tools/nmap", "/api/tools/http-framework", "/api/tools/ffuf"]


def test_unmapped_tool_passes_through() -> None:
    seen: list[str] = []
    hands = _hands_capturing(seen)
    hands.call("api_fuzzer", {"target": "x"})
    assert seen == ["/api/tools/api_fuzzer"]
