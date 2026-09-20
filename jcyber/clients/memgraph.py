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

    def bootstrap_engagement(
        self, engagement_id: str, target: str, scope_items: list[dict[str, str]]
    ) -> None:
        """Create the Engagement node and insert scope nodes if they don't exist.
        Idempotent — safe to call on an already-bootstrapped engagement."""
        with self._driver.session() as s:
            s.run(
                "MERGE (e:Engagement {id: $eid}) "
                "SET e.target=$target, e.status='active', e.phase='recon'",
                eid=engagement_id,
                target=target,
            )
            for item in scope_items:
                s.run(
                    "MERGE (sc:Scope {engagement_id: $eid, value: $val}) "
                    "SET sc.kind=$kind, sc.in_scope=true",
                    eid=engagement_id,
                    val=item.get("value", ""),
                    kind=item.get("kind", "host"),
                )

    def project_state(self, engagement_id: str) -> JSON:
        # Core state: phase, hypotheses, validated findings
        cypher_core = (
            "MATCH (e:Engagement {id: $eid}) "
            "OPTIONAL MATCH (h:Hypothesis {engagement_id: $eid, status: 'open'}) "
            "OPTIONAL MATCH (f:Finding {engagement_id: $eid, status: 'validated'}) "
            "RETURN e.phase AS phase, collect(DISTINCT h.id) AS open_hypotheses, "
            "collect(DISTINCT f.id) AS validated_findings"
        )
        # Recent evidence: bounded to last 20 by id (cheapest ordering)
        cypher_evidence = (
            "MATCH (ev:Evidence {engagement_id: $eid}) "
            "RETURN ev.id AS id, ev.tool AS tool, ev.target AS target, ev.summary AS summary "
            "ORDER BY ev.id DESC LIMIT 20"
        )
        # Tools already run: distinct tool names from evidence
        cypher_tools = (
            "MATCH (ev:Evidence {engagement_id: $eid}) "
            "RETURN collect(DISTINCT ev.tool) AS tools_run"
        )
        # Unscored findings: need G3 severity scoring
        cypher_unscored = (
            "MATCH (f:Finding {engagement_id: $eid}) "
            "WHERE f.severity IS NULL "
            "RETURN collect(DISTINCT f.id) AS unscored_findings"
        )
        with self._driver.session() as s:
            rec = s.run(cypher_core, eid=engagement_id).single()
            ev_rows = list(s.run(cypher_evidence, eid=engagement_id))
            tools_rec = s.run(cypher_tools, eid=engagement_id).single()
            unscored_rec = s.run(cypher_unscored, eid=engagement_id).single()
        if rec is None:
            return {
                "phase": "intake",
                "open_hypotheses": [],
                "validated_findings": [],
                "recent_evidence": [],
                "tools_run": [],
                "unscored_findings": [],
            }
        evidence: list[JSON] = [
            {"id": r["id"], "tool": r["tool"], "target": r["target"], "summary": r["summary"]}
            for r in ev_rows
        ]
        tools_run: list[JSON] = list(tools_rec["tools_run"]) if tools_rec else []
        unscored: list[JSON] = list(unscored_rec["unscored_findings"]) if unscored_rec else []
        result: dict[str, JSON] = {
            "phase": rec["phase"],
            "open_hypotheses": list(rec["open_hypotheses"]),
            "validated_findings": list(rec["validated_findings"]),
            "recent_evidence": evidence,
            "tools_run": tools_run,
            "unscored_findings": unscored,
        }
        return result

    def report_data(self, engagement_id: str) -> JSON:
        cypher = (
            "MATCH (f:Finding {engagement_id: $eid, status: 'validated'}) "
            "OPTIONAL MATCH (h:Hypothesis)-[:DERIVES]->(f) "
            "OPTIONAL MATCH (h)-[:SUPPORTED_BY]->(e:Evidence) "
            "RETURN f.id AS id, f.title AS title, f.severity AS severity, "
            "f.justification AS justification, "
            "collect(DISTINCT {id: e.id, tool: e.tool, summary: e.summary}) AS evidence "
            "ORDER BY id"
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
        ts = record.get("ts", "") if isinstance(record, dict) else ""
        with self._driver.session() as s:
            s.run(
                "CREATE (:Decision {engagement_id: $eid, ts: $ts, payload: $payload})",
                eid=engagement_id,
                ts=ts,
                payload=json.dumps(record),
            )

    def decision_log(self, engagement_id: str) -> list[JSON]:
        with self._driver.session() as s:
            rows = list(
                s.run(
                    "MATCH (d:Decision {engagement_id: $eid}) "
                    "RETURN d.payload AS payload ORDER BY d.ts",
                    eid=engagement_id,
                )
            )
        out: list[JSON] = []
        for r in rows:
            try:
                out.append(json.loads(r["payload"]))
            except (ValueError, TypeError):
                continue
        return out

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

    def create_hypothesis(self, engagement_id: str, hid: str, text: str, evidence_id: str) -> None:
        with self._driver.session() as s:
            s.run(
                "MERGE (h:Hypothesis {engagement_id: $eid, id: $hid}) "
                "SET h.text=$text, h.status='open', h.support=0.5 "
                "WITH h "
                "MATCH (ev:Evidence {engagement_id: $eid, id: $evid}) "
                "MERGE (h)-[:SUPPORTED_BY]->(ev)",
                eid=engagement_id,
                hid=hid,
                text=text,
                evid=evidence_id,
            )

    def create_finding(self, engagement_id: str, fid: str, title: str, hypothesis_id: str) -> None:
        with self._driver.session() as s:
            s.run(
                "MERGE (f:Finding {engagement_id: $eid, id: $fid}) "
                "SET f.title=$title, f.status='provisional', f.severity=null "
                "WITH f "
                "MATCH (h:Hypothesis {engagement_id: $eid, id: $hid}) "
                "MERGE (h)-[:DERIVES]->(f)",
                eid=engagement_id,
                fid=fid,
                title=title,
                hid=hypothesis_id,
            )

    def score_finding(self, engagement_id: str, fid: str, severity: int) -> None:
        sev_map = {0: "none", 1: "low", 2: "medium", 3: "high", 4: "critical"}
        label = sev_map.get(severity, "unknown")
        status = "validated" if severity >= 3 else "provisional"
        with self._driver.session() as s:
            s.run(
                "MATCH (f:Finding {engagement_id: $eid, id: $fid}) "
                "SET f.severity=$sev, f.status=$status",
                eid=engagement_id,
                fid=fid,
                sev=label,
                status=status,
            )

    def unscored_findings(self, engagement_id: str) -> list[str]:
        with self._driver.session() as s:
            rows = list(
                s.run(
                    "MATCH (f:Finding {engagement_id: $eid}) "
                    "WHERE f.severity IS NULL "
                    "RETURN f.id AS id",
                    eid=engagement_id,
                )
            )
        return [r["id"] for r in rows]

    def hypothesis_count(self, engagement_id: str) -> int:
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (h:Hypothesis {engagement_id: $eid}) RETURN count(h) AS n",
                eid=engagement_id,
            ).single()
        return int(rec["n"]) if rec else 0

    def finding_count(self, engagement_id: str) -> int:
        with self._driver.session() as s:
            rec = s.run(
                "MATCH (f:Finding {engagement_id: $eid}) RETURN count(f) AS n",
                eid=engagement_id,
            ).single()
        return int(rec["n"]) if rec else 0


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
