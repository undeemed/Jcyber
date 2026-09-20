"""Normalizer: raw tool output -> an Evidence record (sha256 + vault path +
one-line summary). The sha256 is the deterministic dedup pre-check; the vector
band check is a GraphStore concern."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from .types import Evidence


def sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _summarize(raw: str) -> str:
    """Extract a useful summary from tool output. Skip banners, empty lines,
    and decoration. Take up to 3 substantive lines, capped at 300 chars."""
    lines = raw.strip().splitlines()
    # skip common noise: banners, empty, separator lines
    skip = {"starting nmap", "nmap done:", "==", "──", "───", "╭", "╰", "├"}
    useful: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if any(low.startswith(s) for s in skip):
            continue
        if len(stripped) < 3:
            continue
        useful.append(stripped)
        if len(useful) >= 3:
            break
    return " | ".join(useful)[:300] if useful else "(empty output)"


def normalize(engagement_id: str, tool: str, target: str, raw: str, ev_id: str) -> Evidence:
    sha = sha256_hex(raw)
    return Evidence(
        engagement_id=engagement_id,
        id=ev_id,
        tool=tool,
        target=target,
        ts=datetime.now(UTC).isoformat(),
        summary=_summarize(raw),
        sha256=sha,
        raw_path=f"evidence/raw/{sha}.txt",
    )
