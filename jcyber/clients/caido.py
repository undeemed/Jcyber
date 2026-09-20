# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Caido proxy adapter. Reads passive-plugin findings for this engagement's
project; passive only, and its verdicts enter the normalizer as evidence,
never as decisions. Query verified against the Caido GraphQL schema
(github.com/caido/schemas, schemas/proxy/schema.graphql): findings is a
project-scoped connection (Query.findings(first,...): FindingConnection!),
so the project is bound at connect time, not passed as a query argument."""

from __future__ import annotations

import httpx

from jcyber.types import JSON

_FINDINGS_QUERY = (
    "query Findings($first: Int) { findings(first: $first) "
    "{ nodes { id title host path reporter dedupeKey createdAt } } }"
)


class CaidoProxy:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    @classmethod
    def connect(cls, base_url: str, token: str | None = None) -> CaidoProxy:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return cls(httpx.Client(base_url=base_url, headers=headers, timeout=30.0))

    def close(self) -> None:
        self._client.close()

    def findings(self, engagement_id: str, limit: int = 100) -> list[JSON]:
        # Caido scopes findings to the connected project (one project per
        # engagement, bound at connect), so engagement_id is not a query arg.
        resp = self._client.post(
            "/graphql",
            json={"query": _FINDINGS_QUERY, "variables": {"first": limit}},
        )
        resp.raise_for_status()
        payload: object = resp.json()
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        conn = data.get("findings") if isinstance(data, dict) else None
        nodes = conn.get("nodes") if isinstance(conn, dict) else None
        return [n for n in nodes if isinstance(n, dict)] if isinstance(nodes, list) else []


class NullProxy:
    """No Caido API configured: the loop still runs, ingesting no proxy
    findings. Lets the live path come up without the Caido substrate."""

    def findings(self, engagement_id: str) -> list[JSON]:
        return []

    def close(self) -> None:
        return None
