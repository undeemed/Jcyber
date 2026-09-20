"""Jcyber CLI — MCP server for agent-driven pentesting.

Commands:
  serve              Start the MCP server (stdio transport). Connect your
                     agent harness (Claude Code, etc.) to this server.
  run <link>         Convenience: intake a target, start the MCP server,
                     and print connection instructions.
  report <dir>       Render the engagement report from Memgraph.
  trace <dir>        Render the decision trace from Memgraph.
  intake <link>      Create engagement directory from a bare link (no server).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

USAGE = """\
usage: python -m jcyber <command> [args]

commands:
  serve                Start the MCP server (stdio transport)
  run <link>           Intake target + start MCP server
  report <dir>         Render engagement report
  trace <dir>          Render decision trace
  intake <link> [dir]  Create engagement directory from URL
"""


def run_serve() -> int:
    """Start the MCP server for agent harness connection."""
    from .mcp_server import run_server

    run_server()
    return 0


def run_target(args: list[str]) -> int:
    """Intake a target and start the MCP server."""
    if not args:
        print("usage: python -m jcyber run <url>", file=sys.stderr)
        return 2
    link = args[0]
    severity = "critical"
    if len(args) > 1 and args[1] in {"critical", "high", "medium", "low", "none"}:
        severity = args[1]

    from .clients.toon import CliToonCodec
    from .intake import default_engagement_json, intake_link

    result = intake_link(link, severity)
    codec = CliToonCodec()

    # Create engagement directory
    home = Path(os.environ.get("JCYBER_ENGAGEMENTS", "engagements")) / result.slug
    home.mkdir(parents=True, exist_ok=True)
    (home / "evidence" / "raw").mkdir(parents=True, exist_ok=True)

    # Write scope.toon
    scope_path = home / "scope.toon"
    if not scope_path.exists():
        scope_path.write_text(codec.encode(result.scope_json))
        print(f"[jcyber] wrote {scope_path}", file=sys.stderr)

    # Write engagement.toon
    eng_path = home / "engagement.toon"
    if not eng_path.exists():
        eng_json = default_engagement_json(result.host, result.slug)
        eng_path.write_text(codec.encode(eng_json))
        print(f"[jcyber] wrote {eng_path}", file=sys.stderr)

    print(f"[jcyber] engagement: {result.slug}", file=sys.stderr)
    print(f"[jcyber] target: {result.host}", file=sys.stderr)
    print(f"[jcyber] severity focus: {severity}", file=sys.stderr)
    print("[jcyber] starting MCP server...", file=sys.stderr)

    # Set engagement ID for the MCP server
    os.environ["JCYBER_ENGAGEMENT_ID"] = result.slug
    os.environ["JCYBER_ENGAGEMENT_DIR"] = str(home)

    from .mcp_server import get_server_state, run_server

    state = get_server_state()
    state.engagement_id = result.slug

    # Load scope and config into server state
    from .config import Engagement, scope_from_json

    state.scope = scope_from_json(result.scope_json)
    state.cfg = Engagement.from_json(default_engagement_json(result.host, result.slug))

    run_server()
    return 0


def run_report(home: Path) -> int:
    from .clients.memgraph import MemgraphStore
    from .clients.toon import CliToonCodec
    from .config import load_engagement
    from .report import render

    codec = CliToonCodec()
    load_engagement(home / "engagement.toon", codec)
    uri = os.environ.get("MEMGRAPH_URI", "bolt://127.0.0.1:7687")
    store = MemgraphStore.connect(uri)
    try:
        data = store.report_data(home.name)
        print(render(data))
    finally:
        store.close()
    return 0


def run_trace(home: Path) -> int:
    from .clients.memgraph import MemgraphStore
    from .clients.toon import CliToonCodec
    from .config import load_engagement
    from .trace import render

    codec = CliToonCodec()
    load_engagement(home / "engagement.toon", codec)
    uri = os.environ.get("MEMGRAPH_URI", "bolt://127.0.0.1:7687")
    store = MemgraphStore.connect(uri)
    try:
        log = store.decision_log(home.name)
        print(render(home.name, log))
    finally:
        store.close()
    return 0


def run_intake(args: list[str]) -> int:
    if not args or args[0] in {"-h", "--help"}:
        print("usage: python -m jcyber intake <link> [dir] [--severity high]", file=sys.stderr)
        return 2

    from .clients.toon import CliToonCodec
    from .intake import default_engagement_json, intake_link

    link = args[0]
    severity = "critical"
    out_dir: Path | None = None

    i = 1
    while i < len(args):
        if args[i] == "--severity" and i + 1 < len(args):
            severity = args[i + 1]
            i += 2
        else:
            out_dir = Path(args[i])
            i += 1

    result = intake_link(link, severity)
    codec = CliToonCodec()

    home = out_dir or Path(os.environ.get("JCYBER_ENGAGEMENTS", "engagements")) / result.slug
    home.mkdir(parents=True, exist_ok=True)
    (home / "evidence" / "raw").mkdir(parents=True, exist_ok=True)

    scope_path = home / "scope.toon"
    scope_path.write_text(codec.encode(result.scope_json))
    print(f"wrote {scope_path}")

    eng_path = home / "engagement.toon"
    eng_json = default_engagement_json(result.host, result.slug)
    eng_path.write_text(codec.encode(eng_json))
    print(f"wrote {eng_path}")

    print(f"engagement: {result.slug}")
    print(f"target: {result.host}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in {"-h", "--help"}:
        print(USAGE)
        return 0

    cmd = argv[1]

    if cmd == "serve":
        return run_serve()

    if cmd == "run":
        return run_target(argv[2:])

    if cmd == "report":
        if len(argv) < 3:
            print("usage: python -m jcyber report <engagement-dir>", file=sys.stderr)
            return 2
        return run_report(Path(argv[2]))

    if cmd == "trace":
        if len(argv) < 3:
            print("usage: python -m jcyber trace <engagement-dir>", file=sys.stderr)
            return 2
        return run_trace(Path(argv[2]))

    if cmd == "intake":
        return run_intake(argv[2:])

    print(f"unknown command: {cmd}", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
