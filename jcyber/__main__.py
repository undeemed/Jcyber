"""Live engagement entrypoint: wire the real adapters from an engagement
directory and drive the loop. Prerequisites and bring-up are in
docs/RUNBOOK.md. This is the P2 live path -- it talks to real
Memgraph/HexStrike/Jev/TencentDB, so it is exercised under operator
supervision, never in CI.

Three forms:

    python -m jcyber <engagement-dir>   # run the loop
    python -m jcyber intake <link>      # create the engagement dir + scope
                                        # (bare-link default: full scan +
                                        # critical); the operator then authors
                                        # engagement.toon
    python -m jcyber report <engagement-dir>   # render the Markdown report

Caido findings ingestion is wired into the loop when CAIDO_API_URL is set (a
NullProxy no-ops it otherwise); engine augmentation (Cerebras) is enabled per
engagement in engagement.toon (jcyber.clients.engine).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .clients.caido import CaidoProxy, NullProxy
from .clients.hexstrike import HexStrikeHands
from .clients.jev import JevDecider
from .clients.memgraph import MemgraphStore
from .clients.tencentdb import TencentMemory
from .clients.toon import CliToonCodec
from .config import load_engagement, load_scope
from .intake import Intake, intake_link
from .loop import Iteration, Loop
from .report import render
from .trace import render as render_trace

USAGE = (
    "usage: python -m jcyber <engagement-dir>\n"
    "       python -m jcyber intake <link> [--sev SEVERITY]\n"
    "       python -m jcyber report <engagement-dir>\n"
    "       python -m jcyber trace <engagement-dir>"
)


def run_engagement(home: Path) -> list[Iteration]:
    codec = CliToonCodec()
    cfg = load_engagement(home / "engagement.toon", codec)
    scope = load_scope(home / "scope.toon", codec)

    graph = MemgraphStore.connect(os.environ.get("MEMGRAPH_URI", "bolt://127.0.0.1:7687"))
    hands = HexStrikeHands.connect(os.environ.get("HEXSTRIKE_URL", "http://127.0.0.1:8888"))
    decider = JevDecider.from_env(model=cfg.jev_model)
    memory = TencentMemory.connect(os.environ["JCYBER_MEMORY_URL"])
    caido_url = os.environ.get("CAIDO_API_URL")
    proxy = (
        CaidoProxy.connect(caido_url, os.environ.get("CAIDO_API_TOKEN"))
        if caido_url
        else NullProxy()
    )

    # recall priors once, at intake -- read at recall, never in the hot path
    priors = memory.recall(scope.engagement, {"scope": scope.engagement})

    loop = Loop(
        engagement_id=scope.engagement,
        cfg=cfg,
        scope=scope,
        decider=decider,
        graph=graph,
        hands=hands,
        memory=memory,
        proxy=proxy,
        priors=priors,
    )
    try:
        return loop.run()
    finally:
        graph.close()
        hands.close()
        memory.close()
        proxy.close()


def run_report(home: Path) -> int:
    codec = CliToonCodec()
    scope = load_scope(home / "scope.toon", codec)
    graph = MemgraphStore.connect(os.environ.get("MEMGRAPH_URI", "bolt://127.0.0.1:7687"))
    try:
        data = graph.report_data(scope.engagement)
    finally:
        graph.close()
    out = home / "reports" / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data))
    print(f"wrote {out}")
    return 0


def run_trace(home: Path) -> int:
    codec = CliToonCodec()
    scope = load_scope(home / "scope.toon", codec)
    graph = MemgraphStore.connect(os.environ.get("MEMGRAPH_URI", "bolt://127.0.0.1:7687"))
    try:
        decisions = graph.decision_log(scope.engagement)
    finally:
        graph.close()
    print(render_trace(scope.engagement, decisions), end="")
    return 0


def run_intake(args: list[str]) -> int:
    if not args or args[0] in {"-h", "--help"}:
        print("usage: python -m jcyber intake <link> [--sev SEVERITY]")
        return 2 if not args else 0
    link = args[0]
    severity = "critical"
    if "--sev" in args:
        i = args.index("--sev")
        if i + 1 >= len(args):
            print("usage: python -m jcyber intake <link> [--sev SEVERITY]")
            return 2
        severity = args[i + 1]
    try:
        intake: Intake = intake_link(link, severity)
    except ValueError as e:
        print(str(e))
        return 2

    codec = CliToonCodec()
    home = Path(os.environ.get("JCYBER_HOME", "./engagements")) / intake.slug
    scope = home / "scope.toon"
    if scope.exists():
        print(f"already exists: {scope}")
        return 1
    home.mkdir(parents=True, exist_ok=True)
    scope.write_text(codec.encode(intake.scope_json).strip("\n") + "\n")
    (home / "engagement.toon.template").write_text(
        "# engagement.toon -- author this (canonically encoded, no edits needed here)\n"
        "# copy the JSON block from schema/storage-layout.md, keep the gate\n"
        "# thresholds exactly as documented, and set target/program to this engagement.\n"
    )
    print(f"created {scope} -- apex + all subdomains in scope, severity: {severity}")
    toon_path = home / "engagement.toon"
    print(f"next: author {toon_path} (JSON shape: schema/storage-layout.md), then run:")
    print(f"  python -m jcyber {home}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in {"-h", "--help"}:
        print(USAGE)
        return 0 if len(argv) > 1 else 2
    if argv[1] == "intake":
        return run_intake(argv[2:])
    if argv[1] == "report":
        if len(argv) != 3:
            print(USAGE)
            return 2
        return run_report(Path(argv[2]))
    if argv[1] == "trace":
        if len(argv) != 3:
            print(USAGE)
            return 2
        return run_trace(Path(argv[2]))
    if len(argv) != 2:
        print(USAGE)
        return 2
    history = run_engagement(Path(argv[1]))
    last = history[-1].gate.outcome.value if history else "none"
    print(f"engagement ran {len(history)} iteration(s); last outcome: {last}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
