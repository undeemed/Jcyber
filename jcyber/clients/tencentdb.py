"""TencentDB long-term-brain adapter (the two-method seam:
schema/tencentdb/memory-interface.md). Read at recall (once, intake), written
at commit (once, close) -- never in the hot path. Backend is swappable
(standalone SQLite today per PLAN D1, hosted TCB later); this adapter speaks
the HTTP form of the seam."""

from __future__ import annotations

import httpx

from jcyber.types import JSON


class TencentMemory:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    @classmethod
    def connect(cls, base_url: str, timeout: float = 30.0) -> TencentMemory:
        return cls(httpx.Client(base_url=base_url, timeout=timeout))

    def close(self) -> None:
        self._client.close()

    def recall(self, engagement_id: str, scope: JSON) -> JSON:
        resp = self._client.post("/recall", json={"engagement": engagement_id, "scope": scope})
        resp.raise_for_status()
        result: JSON = resp.json()
        return result

    def commit(self, engagement_id: str, atoms: JSON) -> None:
        resp = self._client.post("/commit", json={"engagement": engagement_id, "outbox": atoms})
        resp.raise_for_status()
