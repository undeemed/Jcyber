"""Decision trace: a readable audit of the :Decision log for an engagement.
Pure function of GraphStore.decision_log output - the audit lives in the graph
(PLAN.md section 7), this just renders it so an operator can see, per
iteration, what Jev chose, how confident it was, and how the gate ruled."""

from __future__ import annotations

from .types import JSON


def _n(v: JSON) -> str:
    return f"{v:.2f}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def render(engagement: str, decisions: list[JSON]) -> str:
    lines = [f"# Jcyber trace: {engagement}", f"{len(decisions)} decision(s)", ""]
    for i, d in enumerate(decisions, 1):
        if not isinstance(d, dict):
            continue
        action = d.get("action", "?")
        outcome = d.get("outcome", "?")
        target = d.get("target", "")
        conf = _n(d.get("next_action_conf", ""))
        scope = _n(d.get("scope_safe", ""))
        rr = _n(d.get("report_ready", ""))
        lines.append(
            f"{i:04d}  {str(action):14s} {str(outcome):14s} "
            f"conf={conf} scope={scope} rr={rr}  {target}"
        )
        reason = d.get("reason", "")
        if outcome != "auto" and reason:
            lines.append(f"        reason: {reason}")
    return "\n".join(lines).rstrip() + "\n"
