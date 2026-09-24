# pyright: reportPrivateUsage=false
"""Preflight service checks — connect_backends must probe each service with
real network I/O and block when any is unreachable.  Also covers .env loading
(the root cause of the original "missing TYPESAFE_API_KEY" report)."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _clean_state():
    from jcyber.mcp_server import _state

    _state.hands = None
    _state.graph = None
    _state.caido = None
    _state.memory = None


@pytest.fixture(autouse=True)
def _reset_state():
    _clean_state()
    yield
    _clean_state()


# -- env that satisfies every check ----------------------------------------
_FULL_ENV = {
    "HEXSTRIKE_URL": "http://127.0.0.1:8888",
    "MEMGRAPH_URI": "bolt://127.0.0.1:7687",
    "JCYBER_MEMORY_URL": "http://127.0.0.1:9999",
    "CAIDO_PROXY": "127.0.0.1:8889",
    "CAIDO_API_URL": "http://127.0.0.1:8080",
    "CAIDO_API_TOKEN": "tok",
    "TYPESAFE_API_KEY": "key",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_all_ok():
    """Context manager stack: every backend connects and pings OK."""
    return (
        patch("jcyber.mcp_server.HexStrikeHands.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.MemgraphStore.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.CaidoProxy.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.TencentMemory.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server._tcp_probe"),  # Caido proxy TCP - success
    )


# ---------------------------------------------------------------------------
# All services up → no prompt
# ---------------------------------------------------------------------------


def test_all_services_up_no_prompt():
    from jcyber.mcp_server import connect_backends

    patches = _patch_all_ok()
    with (
        patch.dict(os.environ, _FULL_ENV, clear=True),
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patch("jcyber.mcp_server._prompt_continue") as mock_prompt,
    ):
        connect_backends()
        mock_prompt.assert_not_called()


# ---------------------------------------------------------------------------
# HexStrike .ping() failure → prompt (not just .connect())
# ---------------------------------------------------------------------------


def test_hexstrike_ping_fails_triggers_prompt():
    from jcyber.mcp_server import connect_backends

    hands = MagicMock()
    hands.ping.side_effect = ConnectionError("refused")

    with (
        patch.dict(os.environ, _FULL_ENV, clear=True),
        patch("jcyber.mcp_server.HexStrikeHands.connect", return_value=hands),
        patch("jcyber.mcp_server.MemgraphStore.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.CaidoProxy.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.TencentMemory.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server._tcp_probe"),
        patch("jcyber.mcp_server._prompt_continue") as mock_prompt,
    ):
        connect_backends()
        mock_prompt.assert_called_once()
        errors = mock_prompt.call_args[0][0]
        assert any("HexStrike" in e for e in errors)


# ---------------------------------------------------------------------------
# Caido proxy TCP probe failure → prompt
# ---------------------------------------------------------------------------


def test_caido_proxy_tcp_fail_triggers_prompt():
    from jcyber.mcp_server import connect_backends

    with (
        patch.dict(os.environ, _FULL_ENV, clear=True),
        patch("jcyber.mcp_server.HexStrikeHands.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.MemgraphStore.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.CaidoProxy.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.TencentMemory.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server._tcp_probe", side_effect=ConnectionRefusedError("refused")),
        patch("jcyber.mcp_server._prompt_continue") as mock_prompt,
    ):
        connect_backends()
        mock_prompt.assert_called_once()
        errors = mock_prompt.call_args[0][0]
        assert any("Caido proxy" in e for e in errors)


# ---------------------------------------------------------------------------
# Caido API .ping() failure → prompt (distinct from proxy check)
# ---------------------------------------------------------------------------


def test_caido_api_ping_fails_triggers_prompt():
    from jcyber.mcp_server import connect_backends

    caido = MagicMock()
    caido.ping.side_effect = ConnectionError("refused")

    with (
        patch.dict(os.environ, _FULL_ENV, clear=True),
        patch("jcyber.mcp_server.HexStrikeHands.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.MemgraphStore.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.CaidoProxy.connect", return_value=caido),
        patch("jcyber.mcp_server.TencentMemory.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server._tcp_probe"),
        patch("jcyber.mcp_server._prompt_continue") as mock_prompt,
    ):
        connect_backends()
        mock_prompt.assert_called_once()
        errors = mock_prompt.call_args[0][0]
        assert any("Caido API" in e for e in errors)


# ---------------------------------------------------------------------------
# Missing env vars → prompt
# ---------------------------------------------------------------------------


def test_missing_env_vars_trigger_prompt():
    from jcyber.mcp_server import connect_backends

    env = {k: v for k, v in _FULL_ENV.items() if k not in ("TYPESAFE_API_KEY", "JCYBER_MEMORY_URL")}

    with (
        patch.dict(os.environ, env, clear=True),
        patch("jcyber.mcp_server.HexStrikeHands.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.MemgraphStore.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server.CaidoProxy.connect", return_value=MagicMock()),
        patch("jcyber.mcp_server._tcp_probe"),
        patch("jcyber.mcp_server._prompt_continue") as mock_prompt,
    ):
        connect_backends()
        mock_prompt.assert_called_once()
        errors = mock_prompt.call_args[0][0]
        assert any("TYPESAFE_API_KEY" in e for e in errors)
        assert any("JCYBER_MEMORY_URL" in e for e in errors)


# ---------------------------------------------------------------------------
# _prompt_continue: operator answers y/n/headless/noninteractive
# ---------------------------------------------------------------------------


def test_prompt_aborts_on_no(tmp_path: Path) -> None:
    from jcyber.mcp_server import _prompt_continue

    fake_tty = tmp_path / "tty"
    fake_tty.write_text("n\n")

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("builtins.open", return_value=open(fake_tty)),
        pytest.raises(SystemExit, match="1"),
    ):
        _prompt_continue(["HexStrike down"])


def test_prompt_continues_on_yes(tmp_path: Path) -> None:
    from jcyber.mcp_server import _prompt_continue

    fake_tty = tmp_path / "tty"
    fake_tty.write_text("y\n")

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("builtins.open", return_value=open(fake_tty)),
    ):
        _prompt_continue(["HexStrike down"])  # should not raise


def test_prompt_continues_headless():
    """No terminal available → continue with degraded services (auto-continue)."""
    from jcyber.mcp_server import _prompt_continue

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("builtins.open", side_effect=OSError("no tty")),
    ):
        # should return normally, not raise SystemExit
        _prompt_continue(["HexStrike down"])


def test_noninteractive_aborts_without_prompt():
    """JCYBER_NONINTERACTIVE=1 → abort immediately, never open /dev/tty."""
    from jcyber.mcp_server import _prompt_continue

    with (
        patch.dict(os.environ, {"JCYBER_NONINTERACTIVE": "1"}, clear=True),
        patch("builtins.open") as mock_open,
        pytest.raises(SystemExit, match="1"),
    ):
        _prompt_continue(["HexStrike down"])
    mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# TCP probe unit test
# ---------------------------------------------------------------------------


def test_tcp_probe_success():
    """TCP probe succeeds against a listening socket."""
    from jcyber.mcp_server import _tcp_probe

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        _tcp_probe("127.0.0.1", port)  # should not raise
    finally:
        srv.close()


def test_tcp_probe_refuses():
    """TCP probe raises when port is closed."""
    from jcyber.mcp_server import _tcp_probe

    with pytest.raises(ConnectionRefusedError):
        # port 1 is almost certainly not listening
        _tcp_probe("127.0.0.1", 1, timeout=1.0)


# ---------------------------------------------------------------------------
# .env loading: run_server calls load_dotenv before connect_backends
# ---------------------------------------------------------------------------


def test_run_server_loads_dotenv():
    """run_server must call load_dotenv() before mcp.run()."""
    from jcyber.mcp_server import run_server

    call_order: list[str] = []

    def fake_load_dotenv() -> None:
        call_order.append("load_dotenv")

    def fake_run(**_: object) -> None:
        call_order.append("mcp_run")

    with (
        patch("jcyber.mcp_server.mcp") as mock_mcp,
        patch("jcyber.mcp_server.disconnect_backends"),
    ):
        mock_mcp.run = fake_run
        with patch.dict("sys.modules", {"dotenv": MagicMock(load_dotenv=fake_load_dotenv)}):
            run_server()

    assert call_order == ["load_dotenv", "mcp_run"]
