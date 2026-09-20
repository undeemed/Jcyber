"""Question assembly + answer projection."""

from __future__ import annotations

import pytest

from jcyber.decide import ACTION_OPTIONS, assemble_questions, interpret
from jcyber.types import Answer, ChoiceAns, ChoiceQ, NoulAns, NoulQ


def test_assemble_core_and_hypothesis_questions() -> None:
    q = assemble_questions({"open_hypotheses": ["H-003"]})
    assert set(q) == {"next_action", "scope_safe", "report_ready", "h_H-003_supported"}
    na = q["next_action"]
    assert isinstance(na, ChoiceQ)
    assert set(na.options) == set(ACTION_OPTIONS)
    assert isinstance(q["scope_safe"], NoulQ)


def test_assemble_without_open_hypotheses() -> None:
    q = assemble_questions({"open_hypotheses": []})
    assert set(q) == {"next_action", "scope_safe", "report_ready"}


def test_interpret_projects_typed_answers() -> None:
    answers: dict[str, Answer] = {
        "next_action": ChoiceAns(
            choice="probing", confidence=0.93, probabilities={"probing": 0.93}
        ),
        "scope_safe": NoulAns(noul=0.96),
        "report_ready": NoulAns(noul=0.21),
        "h_H-003_supported": NoulAns(noul=0.92),
    }
    d = interpret(answers)
    assert d.next_action.choice == "probing"
    assert d.scope_safe.noul == 0.96
    assert d.supports["h_H-003_supported"].noul == 0.92


def test_interpret_rejects_wrong_answer_type() -> None:
    answers: dict[str, Answer] = {
        "next_action": NoulAns(noul=0.5),  # should be a choice
        "scope_safe": NoulAns(noul=0.9),
        "report_ready": NoulAns(noul=0.2),
    }
    with pytest.raises(TypeError):
        interpret(answers)
