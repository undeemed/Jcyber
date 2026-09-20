"""The decision gate: deterministic scope first, then the modeled scope
floor, then per-class confidence. Mirrors orchestrator/loop.md section 1 and
config/decision-catalog.md G0/G1. Every threshold comes from cfg (loaded from
engagement.toon); none is hard-coded here."""

from __future__ import annotations

from .config import Engagement
from .scope import in_scope, violates_no_fuzzing
from .types import ActionClass, Decision, GateResult, Outcome, Scope


def evaluate(target: str, decision: Decision, cfg: Engagement, scope: Scope) -> GateResult:
    action = ActionClass(decision.next_action.choice)  # closed set; raises on a bad choice

    # layer 1 -- deterministic scope, non-jailbreakable, runs before the model
    if not in_scope(target, scope):
        return GateResult(Outcome.blocked, action, "deterministic out-of-scope")
    if action is ActionClass.fuzzing and violates_no_fuzzing(target, scope):
        return GateResult(Outcome.blocked, action, "no_fuzzing_on violation")

    # layer 2 -- modeled scope floor; below floor queues, never rejects outright
    floor = cfg.gates["scope_model_floor"].auto
    if decision.scope_safe.noul < floor:
        return GateResult(
            Outcome.confirm_parked,
            action,
            f"scope_safe {decision.scope_safe.noul:.2f} < floor {floor}",
        )

    # exploit is never auto, regardless of confidence (PLAN section 4.4)
    if action is ActionClass.exploit:
        return GateResult(Outcome.confirm_parked, action, "exploit never auto")

    # commit is terminal: no class gate, no tool run
    if action is ActionClass.commit:
        return GateResult(Outcome.auto, action, "commit terminal")

    # per-class confidence gate
    gate = cfg.gates.get(action.value)
    if gate is None:
        return GateResult(Outcome.confirm_parked, action, f"no class gate for {action.value}")
    conf = decision.next_action.confidence
    if conf < gate.auto:
        return GateResult(
            Outcome.confirm_parked, action, f"conf {conf:.2f} < {gate.auto} -> {gate.fallback}"
        )
    return GateResult(Outcome.auto, action, "auto")
