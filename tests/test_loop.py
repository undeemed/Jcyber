"""End-to-end loop iteration + the bounded run() driver, all seams faked:
auto acts + stores + applies verdicts; out-of-scope blocks; low scope_safe
parks; run() closes on report-ready, stops on commit, halts on three stalls."""

from __future__ import annotations

from jcyber.config import Engagement
from jcyber.loop import Loop
from jcyber.types import JSON, ActionClass, Answer, ChoiceAns, NoulAns, Outcome, Scope
from tests.fakes import FakeDecider, FakeGraph, FakeHands, FakeMemory

PROJ: dict[str, JSON] = {
    "phase": "probing",
    "open_hypotheses": ["H-003"],
    "validated_findings": [],
    "focus_target": "https://acme-lab.example/api/users/4821",
}


def _answers(
    action: str,
    conf: float,
    scope_safe: float,
    support: float = 0.92,
    report_ready: float = 0.21,
) -> dict[str, Answer]:
    return {
        "next_action": ChoiceAns(choice=action, confidence=conf, probabilities={action: conf}),
        "scope_safe": NoulAns(noul=scope_safe),
        "report_ready": NoulAns(noul=report_ready),
        "h_H-003_supported": NoulAns(noul=support),
    }


def _loop(
    cfg: Engagement, scope: Scope, answers: dict[str, Answer], projection: JSON
) -> tuple[Loop, FakeGraph, FakeHands]:
    graph = FakeGraph(projection)
    hands = FakeHands("PORT 80 open")
    loop = Loop(
        engagement_id="acme-lab",
        cfg=cfg,
        scope=scope,
        decider=FakeDecider(answers),
        graph=graph,
        hands=hands,
        memory=FakeMemory(),
    )
    return loop, graph, hands


def test_auto_iteration_acts_stores_and_promotes(cfg: Engagement, scope: Scope) -> None:
    loop, graph, hands = _loop(cfg, scope, _answers("probing", 0.93, 0.96), PROJ)
    it = loop.iterate()
    assert it.gate.outcome is Outcome.auto
    assert it.gate.action_class is ActionClass.probing
    assert [t for t, _ in hands.calls] == ["nuclei_scan"]
    assert len(graph.evidence) == 1
    assert graph.verdicts == [("H-003", "promote", 0.92)]
    assert len(graph.decisions) == 1


def test_out_of_scope_iteration_blocks(cfg: Engagement, scope: Scope) -> None:
    proj: dict[str, JSON] = {**PROJ, "focus_target": "https://staging.acme-lab.example/x"}
    loop, graph, hands = _loop(cfg, scope, _answers("probing", 0.93, 0.96), proj)
    it = loop.iterate()
    assert it.gate.outcome is Outcome.blocked
    assert hands.calls == []
    assert graph.evidence == []
    assert graph.verdicts == []


def test_low_scope_safe_parks_without_acting(cfg: Engagement, scope: Scope) -> None:
    loop, _, hands = _loop(cfg, scope, _answers("probing", 0.93, 0.50), PROJ)
    it = loop.iterate()
    assert it.gate.outcome is Outcome.confirm_parked
    assert hands.calls == []


def test_low_support_retires_hypothesis(cfg: Engagement, scope: Scope) -> None:
    loop, graph, _ = _loop(cfg, scope, _answers("probing", 0.93, 0.96, support=0.10), PROJ)
    loop.iterate()
    assert graph.verdicts == [("H-003", "retire", 0.10)]


def test_run_closes_when_report_ready(cfg: Engagement, scope: Scope) -> None:
    # report_ready 0.97 >= cfg.report_ready 0.95 -> close after one iteration.
    loop, _, _ = _loop(cfg, scope, _answers("probing", 0.93, 0.96, report_ready=0.97), PROJ)
    history = loop.run(max_iterations=10)
    assert len(history) == 1
    assert history[-1].close is True


def test_run_halts_after_three_stalls(cfg: Engagement, scope: Scope) -> None:
    # low scope_safe parks every iteration -> three consecutive stalls -> halt.
    loop, _, hands = _loop(cfg, scope, _answers("probing", 0.93, 0.50), PROJ)
    history = loop.run(max_iterations=10)
    assert len(history) == 3
    assert all(it.gate.outcome is Outcome.confirm_parked for it in history)
    assert hands.calls == []


def test_run_stops_on_commit(cfg: Engagement, scope: Scope) -> None:
    loop, _, hands = _loop(cfg, scope, _answers("commit", 0.99, 0.99), PROJ)
    history = loop.run(max_iterations=10)
    assert len(history) == 1
    assert history[-1].gate.action_class is ActionClass.commit
    assert hands.calls == []  # commit runs no tool
