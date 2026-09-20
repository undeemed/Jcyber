# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Jev adapter (the only model in the control path). Maps the code-assembled
questions to typesafe_sdk types and projects the response back to jcyber's
typed answers, so no typesafe type leaks past this seam. State is text
(catalog: text-only), so it passes straight through as JSONContent."""

from __future__ import annotations

from collections.abc import Mapping

import typesafe_sdk as ts

from jcyber.types import Answer, ChoiceAns, ChoiceQ, NoulAns, NoulQ, Question, ScoreAns


def _to_ts(q: Question) -> ts.Noul | ts.Choice | ts.Score:
    if isinstance(q, NoulQ):
        return ts.Noul(instructions=q.instructions)
    if isinstance(q, ChoiceQ):
        return ts.Choice(instructions=q.instructions, criteria=dict(q.options))
    return ts.Score(instructions=q.instructions, criteria=list(q.levels))


def _from_ts(a: ts.NoulAnswer | ts.ChoiceAnswer | ts.ScoreAnswer) -> Answer:
    if isinstance(a, ts.NoulAnswer):
        return NoulAns(noul=a.noul)
    if isinstance(a, ts.ChoiceAnswer):
        return ChoiceAns(
            choice=a.choice, confidence=a.confidence, probabilities=dict(a.probabilities)
        )
    return ScoreAns(score=a.score, confidence=a.confidence, probabilities=dict(a.probabilities))


class JevDecider:
    def __init__(self, client: ts.TypeSafeClient, model: str | None = None) -> None:
        self._client = client
        self._model = model

    @classmethod
    def from_env(cls, model: str | None = None) -> JevDecider:
        return cls(ts.TypeSafeClient(), model=model)

    def system_one(self, state: str, questions: Mapping[str, Question]) -> dict[str, Answer]:
        ts_questions = {qid: _to_ts(q) for qid, q in questions.items()}
        resp = self._client.system_one(state, ts_questions, model=self._model)
        return {qid: _from_ts(a) for qid, a in resp.answers.items()}
