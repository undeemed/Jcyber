"""The orchestrator loop. One iteration per tool-run: observe -> decide ->
gate -> act -> store -> learn. Every seam is injected, so the whole loop runs
against fakes in tests and real adapters in production. Mirrors
orchestrator/loop.md section 1.

Engine augmentation (route_via_engine), Caido findings ingestion, and the
TencentDB recall-at-intake / G3 finding-scoring stages are live-wiring (P2):
their ports and adapters exist, but the driver below covers the core chain."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Engagement
from .decide import decide
from .gate import evaluate
from .learn import distill
from .normalize import normalize
from .ports import Decider, GraphStore, Hands, Memory
from .router import route
from .state import build_state
from .types import JSON, ActionClass, Decision, GateResult, Outcome, Scope


@dataclass(frozen=True)
class Iteration:
    gate: GateResult
    close: bool


@dataclass
class Loop:
    engagement_id: str
    cfg: Engagement
    scope: Scope
    decider: Decider
    graph: GraphStore
    hands: Hands
    memory: Memory
    _ev_seq: int = 0

    def _target(self, projection: JSON) -> str:
        if isinstance(projection, dict):
            focus = projection.get("focus_target")
            if isinstance(focus, str) and focus:
                return focus
        return self.cfg.target

    def iterate(self) -> Iteration:
        projection = self.graph.project_state(self.engagement_id)
        state = build_state(projection, self.cfg.state_budget_chars)
        decision = decide(self.decider, state, projection)
        target = self._target(projection)
        result = evaluate(target, decision, self.cfg, self.scope)
        self.graph.write_decision(self.engagement_id, self._record(decision, result, target))
        if result.outcome is Outcome.auto:
            self._act(result.action_class, decision, target, projection)
        return Iteration(gate=result, close=self.should_close(decision))

    def run(self, max_iterations: int | None = None) -> list[Iteration]:
        """Drive iterations until the engagement is ready to report, commit is
        chosen, three consecutive gates make no progress (loop.md halt), or the
        iteration budget is spent. Bounded by construction -- never open-ended.
        """
        # ponytail: cap ~= tool_run budget; precise per-call budget accounting is P2.
        cap = max_iterations if max_iterations is not None else self.cfg.budget.get("tool_runs", 1)
        history: list[Iteration] = []
        stalls = 0
        for _ in range(max(cap, 1)):
            it = self.iterate()
            history.append(it)
            if it.close:
                break
            if it.gate.outcome is Outcome.auto and it.gate.action_class is ActionClass.commit:
                break
            if it.gate.outcome is Outcome.auto:
                stalls = 0
            else:
                stalls += 1
                if stalls >= 3:
                    break
        return history

    def should_close(self, decision: Decision) -> bool:
        return decision.report_ready.noul >= self.cfg.report_ready

    def _act(self, action: ActionClass, decision: Decision, target: str, projection: JSON) -> None:
        if action is ActionClass.commit:
            self._apply_verdicts(decision)
            self.memory.commit(self.engagement_id, distill(projection))
            return
        if action is ActionClass.report:
            return  # local renderer, not a HexStrike tool
        call = route(action, target, self.cfg, self.scope)
        if call is None:
            return
        raw = self.hands.call(call.tool, call.params)
        self._ev_seq += 1
        ev = normalize(self.engagement_id, call.tool, target, raw, f"E-{self._ev_seq:03d}")
        if not self.graph.seen_sha256(self.engagement_id, ev.sha256):
            self.graph.insert_evidence(ev)
        self._apply_verdicts(decision)

    def _apply_verdicts(self, decision: Decision) -> None:
        promote, retire = self.cfg.verdicts.promote, self.cfg.verdicts.retire
        for qid, ans in decision.supports.items():
            hid = qid[len("h_") : -len("_supported")]
            if ans.noul >= promote:
                self.graph.apply_verdict(self.engagement_id, hid, "promote", ans.noul)
            elif ans.noul <= retire:
                self.graph.apply_verdict(self.engagement_id, hid, "retire", ans.noul)

    def _record(self, decision: Decision, result: GateResult, target: str) -> JSON:
        return {
            "target": target,
            "action": result.action_class.value,
            "outcome": result.outcome.value,
            "reason": result.reason,
            "next_action_conf": decision.next_action.confidence,
            "scope_safe": decision.scope_safe.noul,
            "report_ready": decision.report_ready.noul,
        }
