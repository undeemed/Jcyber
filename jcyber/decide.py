"""Decide: assemble the catalog questions in code (never in the model) and
project the Jev response into a typed Decision. One system_one call per
iteration; each question is one atomic gut-check (AGENTS.md invariant #4)."""

from __future__ import annotations

from collections.abc import Mapping

from .ports import Decider
from .types import JSON, Answer, ChoiceAns, ChoiceQ, Decision, NoulAns, NoulQ, Question

# next_action options (config/decision-catalog.md G1). Assembled in code.
ACTION_OPTIONS: dict[str, str] = {
    "recon_passive": "enumerate without touching the target (subdomains, OSINT)",
    "recon_active": "contact the target lightly (port scan, fingerprint, dirb)",
    "probing": "targeted test of a specific open hypothesis",
    "fuzzing": "high-volume payload/param fuzzing on a confirmed surface",
    "verify": "re-run a minimal PoC to confirm a finding still holds",
    "exploit": "active exploitation already authorized by the operator",
    "report": "stop probing, prepare the report",
    "commit": "nothing left productive; distill and close",
}


def _open_hypotheses(projection: JSON) -> list[str]:
    if not isinstance(projection, dict):
        return []
    hs = projection.get("open_hypotheses")
    if not isinstance(hs, list):
        return []
    return [h for h in hs if isinstance(h, str)]


def assemble_questions(projection: JSON) -> dict[str, Question]:
    q: dict[str, Question] = {
        "next_action": ChoiceQ(
            "Which single next action best advances the engagement given the state?",
            dict(ACTION_OPTIONS),
        ),
        "scope_safe": NoulQ("How likely is this proposed action unambiguously within scope?"),
        "report_ready": NoulQ("Is the engagement in a state to produce a defensible report now?"),
    }
    for hid in _open_hypotheses(projection):
        q[f"h_{hid}_supported"] = NoulQ(
            f"Given the evidence attached to {hid}, how likely is {hid} true?"
        )
    return q


def _choice(a: Answer) -> ChoiceAns:
    if not isinstance(a, ChoiceAns):
        raise TypeError(f"expected a choice answer, got {type(a).__name__}")
    return a


def _noul(a: Answer) -> NoulAns:
    if not isinstance(a, NoulAns):
        raise TypeError(f"expected a noul answer, got {type(a).__name__}")
    return a


def interpret(answers: Mapping[str, Answer]) -> Decision:
    supports = {
        qid: _noul(a)
        for qid, a in answers.items()
        if qid.startswith("h_") and qid.endswith("_supported")
    }
    return Decision(
        next_action=_choice(answers["next_action"]),
        scope_safe=_noul(answers["scope_safe"]),
        report_ready=_noul(answers["report_ready"]),
        supports=supports,
    )


def decide(decider: Decider, state: str, projection: JSON) -> Decision:
    return interpret(decider.system_one(state, assemble_questions(projection)))
