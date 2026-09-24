# pyright: reportPrivateUsage=false
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


def _hands_returning(response: httpx.Response) -> HexStrikeHands:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    client = httpx.Client(base_url="http://127.0.0.1:8888", transport=httpx.MockTransport(handler))
    return HexStrikeHands(client)


def test_call_surfaces_stdout_from_json_envelope() -> None:
    hands = _hands_returning(
        httpx.Response(200, json={"stdout": "PORT 80 open", "stderr": "", "return_code": 0})
    )
    assert hands.call("nmap_scan", {"target": "x"}) == "PORT 80 open"


def test_call_passes_through_non_json() -> None:
    hands = _hands_returning(httpx.Response(200, text="raw text output"))
    assert hands.call("nmap_scan", {"target": "x"}) == "raw text output"


def test_call_detects_html_proxy_garbage() -> None:
    """If HexStrike returns HTML (e.g. Caido SPA), the call returns a tool_error."""
    html = "<!DOCTYPE html><html><body>Caido Dashboard</body></html>"
    hands = _hands_returning(httpx.Response(200, text=html))
    result = hands.call("nmap_scan", {"target": "x"})
    assert result.startswith("[tool_error]")
    assert "HTML" in result


def test_html_inside_json_envelope_passes_through() -> None:
    """HTML inside the JSON envelope's stdout is legitimate output
    (browser_agent_inspect, http_repeater). Must NOT be flagged as garbage."""
    hands = _hands_returning(
        httpx.Response(
            200, json={"stdout": "<html><body>page content</body></html>", "return_code": 0}
        )
    )
    result = hands.call("browser_agent_inspect", {"target": "x"})
    assert not result.startswith("[tool_error]")
    assert "<html>" in result


def test_call_surfaces_error_from_envelope() -> None:
    """HexStrike envelope with 'error' key surfaces as tool_error."""
    hands = _hands_returning(httpx.Response(200, json={"error": "command not found: wafw00f"}))
    result = hands.call("wafw00f_scan", {"target": "x"})
    assert result.startswith("[tool_error]")
    assert "wafw00f" in result


def test_call_timeout_returns_error() -> None:
    """Timeout returns structured error, not exception."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    client = httpx.Client(base_url="http://127.0.0.1:8888", transport=httpx.MockTransport(handler))
    hands = HexStrikeHands(client)
    result = hands.call("nmap_scan", {"target": "x"})
    assert result.startswith("[tool_error]")
    assert "timed out" in result


def test_fetch_available_tools_parses_health() -> None:
    """fetch_available_tools parses the /health response."""
    health_data = {
        "categories": {
            "recon": {
                "tools": {
                    "nmap": {"installed": True},
                    "subfinder": {"installed": True},
                    "wafw00f": {"installed": False},
                }
            }
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=health_data)
        return httpx.Response(200, text="ok")

    client = httpx.Client(base_url="http://127.0.0.1:8888", transport=httpx.MockTransport(handler))
    hands = HexStrikeHands(client)
    avail = hands.fetch_available_tools()
    assert "nmap" in avail
    assert "subfinder" in avail
    assert "wafw00f" not in avail


def test_is_tool_available() -> None:
    """is_tool_available maps MCP name to slug and checks availability."""
    health_data = {
        "categories": {
            "recon": {
                "tools": {
                    "nmap": {"installed": True},
                    "subfinder": {"installed": True},
                }
            }
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=health_data)
        return httpx.Response(200, text="ok")

    client = httpx.Client(base_url="http://127.0.0.1:8888", transport=httpx.MockTransport(handler))
    hands = HexStrikeHands(client)
    assert hands.is_tool_available("nmap_scan") is True
    assert hands.is_tool_available("subfinder_scan") is True
    assert hands.is_tool_available("wafw00f_scan") is False


def test_per_tool_timeout_used() -> None:
    """Per-tool timeout overrides default."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    client = httpx.Client(base_url="http://127.0.0.1:8888", transport=httpx.MockTransport(handler))
    hands = HexStrikeHands(client, default_timeout=999.0)
    # qsreplace has a 15s timeout override
    hands.call("qsreplace", {"target": "x"})
    # Verify the timeout map exists and has the expected value
    from jcyber.clients.hexstrike import _TOOL_TIMEOUT

    assert _TOOL_TIMEOUT["qsreplace"] == 15
    assert _TOOL_TIMEOUT.get("nmap_scan") == 180
