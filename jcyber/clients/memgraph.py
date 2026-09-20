# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Memgraph session-brain adapter over the Bolt driver (Memgraph is
Bolt-compatible). This is the one adapter the P1 compose smoke exercises:
`python -m jcyber.clients.memgraph --smoke`."""

from __future__ import annotations

import json
import os
import sys

from neo4j import Driver, GraphDatabase

from jcyber.types import JSON, Evidence


class MemgraphStore:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    @classmethod
    def connect(
        cls, uri: str = "bolt://127.0.0.1:7687", auth: tuple[str, str] | None = None
    ) -> MemgraphStore:
        return cls(GraphDatabase.driver(uri, auth=auth))

    def close(self) -> None:
        self._driver.close()

    def ping(self) -> int:
        with self._driver.session() as s:
            rec = s.run("RETURN 1 AS ok").single()
        return int(rec["ok"]) if rec is not None else 0

    def project_state(self, engagement_id: str) -> JSON:
        cypher = (
            "MATCH (e:Engagement {id: $eid}) "
            "OPTIONAL MATCH (h:Hypothesis {engagement_id: $eid, status: 'open'}) "
            "OPTIONAL MATCH (f:Finding {engagement_id: $eid, status: 'validated'}) "
            "RETURN e.phase AS phase, collect(DISTINCT h.id) AS open_hypotheses, "
            "collect(DISTINCT f.id) AS validated_findings"
        )
        with self._driver.session() as s:
            rec = s.run(cypher, eid=engagement_id).single()
        if rec is None:
            return {"phase": "intake", "open_hypotheses": [], "validated_findings": []}
        return {
            "phase": rec["phase"],
            "open_hypotheses": list(rec["open_hypotheses"]),
            "validated_findings": list(rec["validated_findings"]),
        }

    def report_data(self, engagement_id: str) -> JSON:
        cypher = (
            "MATCH (f:Finding {engagement_id: $eid, status: 'validated'}) "
            "OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(e:Evidence) "
            "RETURN f.id AS id, f.title AS title, f.severity AS severity, "
            "f.justification AS justification, "
            "collect(DISTINCT {id: e.id, tool: e.tool, summary: e.summary}) AS evidence "
            "ORDER BY f.id"
        )
        with self._driver.session() as s:
            rows = list(s.run(cypher, eid=engagement_id))
        findings: list[JSON] = [
            {
                "id": r["id"],
                "title": r["title"],
                "severity": r["severity"],
                "justification": r["justification"],
                "evidence": [ev for ev in r["evidence"] if ev.get("id") is not None],
            }
            for r in rows
        ]
        return {"engagement": engagement_id, "findings": findings}

    def write_decision(self, engagement_id: str, record: JSON) -> None:
        with self._driver.session() as s:
            s.run(
                "CREATE (:Decision {engagement_id: $eid, payload: $payload})",
                eid=engagement_id,
                payload=json.dumps(record),
            )

    def insert_evidence(self, ev: Evidence) -> None:
        with self._driver.session() as s:
            s.run(
                "MERGE (e:Evidence {engagement_id: $eid, id: $id}) "
                "SET e.tool=$tool, e.target=$target, e.ts=$ts, e.summary=$summary, "
                "e.sha256=$sha, e.raw_path=$path",
                eid=ev.engagement_id,
                id=ev.id,
                tool=ev.tool,
                target=ev.target,
                ts=ev.ts,
                summary=ev.summary,
                sha=ev.sha256,
                path=ev.raw_path,
            )

    def seen_sha256(self, engagement_id: str, sha256: str) -> bool:
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (e:Evidence {engagement_id: $eid, sha256: $sha}) RETURN count(e) AS n",
                eid=engagement_id,
                sha=sha256,
            ).single()
        return rec is not None and int(rec["n"]) > 0

    def apply_verdict(
        self, engagement_id: str, hypothesis_id: str, verdict: str, support: float
    ) -> None:
        with self._driver.session() as s:
            s.run(
                "MERGE (h:Hypothesis {engagement_id: $eid, id: $hid}) "
                "SET h.status=$verdict, h.support=$support",
                eid=engagement_id,
                hid=hypothesis_id,
                verdict=verdict,
                support=support,
            )


def _main() -> int:
    if "--smoke" not in sys.argv:
        print("usage: python -m jcyber.clients.memgraph --smoke")
        return 2
    uri = os.environ.get("MEMGRAPH_URI", "bolt://127.0.0.1:7687")
    try:
        store = MemgraphStore.connect(uri)
        try:
            ok = store.ping()
        finally:
            store.close()
    except Exception as e:  # noqa: BLE001 - a smoke check reports any connectivity failure
        print(f"memgraph smoke FAILED @ {uri}: {type(e).__name__}: {e}")
        return 1
    print(f"memgraph smoke ok: {ok} @ {uri}")
    return 0 if ok == 1 else 1


if __name__ == "__main__":
    raise SystemExit(_main())
