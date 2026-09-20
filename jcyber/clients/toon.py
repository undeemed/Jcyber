"""TOON codec adapter — shells out to @toon-format/cli. TOON on disk is
always encoder output (AGENTS.md invariant #1); we never hand-format it."""

from __future__ import annotations

import json
import subprocess

from jcyber.types import JSON


class CliToonCodec:
    def __init__(self, cmd: list[str] | None = None) -> None:
        self._cmd = cmd if cmd is not None else ["npx", "-y", "@toon-format/cli"]

    def encode(self, obj: JSON) -> str:
        p = subprocess.run(
            self._cmd, input=json.dumps(obj), capture_output=True, text=True, check=True
        )
        return p.stdout

    def decode(self, text: str) -> JSON:
        p = subprocess.run(
            [*self._cmd, "--decode"], input=text, capture_output=True, text=True, check=True
        )
        result: JSON = json.loads(p.stdout)
        return result
