"""Normalizer: raw tool output -> an Evidence record (sha256 + vault path +
one-line summary). The sha256 is the deterministic dedup pre-check; the vector
band check is a GraphStore concern."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from .types import Evidence


def sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize(engagement_id: str, tool: str, target: str, raw: str, ev_id: str) -> Evidence:
    sha = sha256_hex(raw)
    stripped = raw.strip()
    summary = stripped.splitlines()[0][:200] if stripped else "(empty output)"
    return Evidence(
        engagement_id=engagement_id,
        id=ev_id,
        tool=tool,
        target=target,
        ts=datetime.now(UTC).isoformat(),
        summary=summary,
        sha256=sha,
        raw_path=f"evidence/raw/{sha}.txt",
    )
