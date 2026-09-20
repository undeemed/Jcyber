# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportPrivateUsage=false
"""Integration: exercise MemgraphStore Cypher (project_state, insert_evidence,
apply_verdict, create_hypothesis, create_finding, score_finding) against a live
Memgraph instance.

Skips when Memgraph is unreachable, so the default suite stays green without
Docker; runs for real when `docker compose ... up -d` is live."""

from __future__ import annotations

import pytest

from jcyber.clients.memgraph import MemgraphStore
from jcyber.normalize import normalize

EID = "acme-lab-itest"


def _live_store() -> MemgraphStore:
    store = MemgraphStore.connect("bolt://127.0.0.1:7687")
    try:
        store.ping()
    except Exception:  # noqa: BLE001 - any connectivity failure => skip
        store.close()
        pytest.skip("Memgraph not reachable on bolt://127.0.0.1:7687")
    return store


def _wipe(store: MemgraphStore) -> None:
    with store._driver.session() as s:
        s.run("MATCH (n {engagement_id: $e}) DETACH DELETE n", e=EID)
        s.run("MATCH (n:Engagement {id: $e}) DETACH DELETE n", e=EID)


def test_memgraph_evidence_hypothesis_finding_lifecycle() -> None:
    """Exercise the full graph lifecycle: bootstrap, insert evidence,
    create hypothesis, apply verdict, create finding, score finding."""
    store = _live_store()
    try:
        _wipe(store)
        store.bootstrap_engagement(
            EID, "acme-lab.example", [{"kind": "host", "value": "acme-lab.example"}]
        )

        # Insert evidence
        ev = normalize(EID, "nmap_scan", "acme-lab.example", "22/tcp open ssh", "E-001")
        assert not store.seen_sha256(EID, ev.sha256)
        store.insert_evidence(ev)
        assert store.seen_sha256(EID, ev.sha256)

        # Create hypothesis from evidence
        store.create_hypothesis(EID, "H-001", "SSH on port 22 may be vulnerable", "E-001")
        assert store.hypothesis_count(EID) == 1

        # Promote hypothesis
        store.apply_verdict(EID, "H-001", "promote", 0.92)

        # Create finding
        store.create_finding(EID, "F-001", "SSH weak config", "H-001")
        assert store.finding_count(EID) == 1

        # Score finding
        store.score_finding(EID, "F-001", 3)  # high

        # Project state sees evidence and finding
        state = store.project_state(EID)
        assert isinstance(state, dict)
        recent = state.get("recent_evidence")
        assert isinstance(recent, list)
        assert len(recent) >= 1

        # Report data
        report = store.report_data(EID)
        assert isinstance(report, dict)
    finally:
        _wipe(store)
        store.close()
