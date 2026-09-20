# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Caido proxy adapter. Reads passive-plugin findings for this engagement's
project; passive only, and its verdicts enter the normalizer as evidence,
never as decisions. The exact API endpoint/query is operator-confirmed at
live wiring."""

from __future__ import annotations

import httpx

from jcyber.types import JSON

_FINDINGS_QUERY = "query($project: ID!) { findings(project: $project) { id kind severity } }"


class CaidoProxy:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    @classmethod
    def connect(cls, base_url: str, token: str | None = None) -> CaidoProxy:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return cls(httpx.Client(base_url=base_url, headers=headers, timeout=30.0))

    def close(self) -> None:
        self._client.close()

    def findings(self, engagement_id: str) -> list[JSON]:
        resp = self._client.post(
            "/graphql",
            json={"query": _FINDINGS_QUERY, "variables": {"project": engagement_id}},
        )
        resp.raise_for_status()
        payload: object = resp.json()
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        found = data.get("findings") if isinstance(data, dict) else None
        return [item for item in found] if isinstance(found, list) else []
