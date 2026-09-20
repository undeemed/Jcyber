# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportPrivateUsage=false
"""Integration: drive the real Loop against a live Memgraph, all other seams
faked (no real target is touched). Validates the MemgraphStore Cypher
(project_state / write_decision / insert_evidence / apply_verdict) end-to-end.

Skips when Memgraph is unreachable, so the default suite stays green without
Docker; runs for real when `docker compose ... up -d` is live."""

from __future__ import annotations

import pytest

from jcyber.clients.memgraph import MemgraphStore
from jcyber.config import Engagement, scope_from_json
from jcyber.loop import Loop
from jcyber.types import Answer, ChoiceAns, NoulAns
from tests.conftest import ENGAGEMENT_JSON, SCOPE_JSON
from tests.fakes import FakeDecider, FakeHands, FakeMemory, FakeProxy

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


def test_loop_writes_decision_evidence_and_verdict_to_live_memgraph() -> None:
    store = _live_store()
    try:
        _wipe(store)
        with store._driver.session() as s:
            s.run("CREATE (:Engagement {id: $e, phase: 'probing'})", e=EID)
            s.run("CREATE (:Hypothesis {engagement_id: $e, id: 'H-003', status: 'open'})", e=EID)

        answers: dict[str, Answer] = {
            "next_action": ChoiceAns(
                choice="probing", confidence=0.93, probabilities={"probing": 0.93}
            ),
            "scope_safe": NoulAns(noul=0.96),
            "report_ready": NoulAns(noul=0.21),
            "h_H-003_supported": NoulAns(noul=0.92),
        }
        loop = Loop(
            engagement_id=EID,
            cfg=Engagement.from_json(ENGAGEMENT_JSON),
            scope=scope_from_json(SCOPE_JSON),
            decider=FakeDecider(answers),
            graph=store,
            hands=FakeHands("PORT 80 open"),
            memory=FakeMemory(),
            proxy=FakeProxy(),
        )
        it = loop.iterate()
        assert it.gate.outcome.value == "auto"

        with store._driver.session() as s:
            dec = s.run(
                "MATCH (d:Decision {engagement_id: $e}) RETURN count(d) AS n", e=EID
            ).single()
            ev = s.run(
                "MATCH (e:Evidence {engagement_id: $e}) RETURN count(e) AS n", e=EID
            ).single()
            hyp = s.run(
                "MATCH (h:Hypothesis {engagement_id: $e, id: 'H-003'}) RETURN h.status AS st",
                e=EID,
            ).single()
        assert dec is not None and dec["n"] == 1
        assert ev is not None and ev["n"] == 1
        assert hyp is not None and hyp["st"] == "promote"
    finally:
        _wipe(store)
        store.close()
