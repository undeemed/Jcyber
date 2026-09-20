"""In-memory fakes for the ports. The loop is driven entirely through these,
so tests touch no external system."""

from __future__ import annotations

from collections.abc import Mapping

from jcyber.types import JSON, Answer, Evidence, Question


class FakeDecider:
    def __init__(self, answers: dict[str, Answer]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, dict[str, Question]]] = []

    def system_one(self, state: str, questions: Mapping[str, Question]) -> dict[str, Answer]:
        self.calls.append((state, dict(questions)))
        return dict(self.answers)


class FakeGraph:
    def __init__(self, projection: JSON | None = None) -> None:
        self.projection: JSON = (
            projection
            if projection is not None
            else {"phase": "probing", "open_hypotheses": [], "validated_findings": []}
        )
        self.decisions: list[JSON] = []
        self.evidence: list[Evidence] = []
        self.verdicts: list[tuple[str, str, float]] = []
        self._seen: set[str] = set()

    def project_state(self, engagement_id: str) -> JSON:
        return self.projection

    def write_decision(self, engagement_id: str, record: JSON) -> None:
        self.decisions.append(record)

    def insert_evidence(self, ev: Evidence) -> None:
        self.evidence.append(ev)
        self._seen.add(ev.sha256)

    def seen_sha256(self, engagement_id: str, sha256: str) -> bool:
        return sha256 in self._seen

    def apply_verdict(
        self, engagement_id: str, hypothesis_id: str, verdict: str, support: float
    ) -> None:
        self.verdicts.append((hypothesis_id, verdict, support))


class FakeHands:
    def __init__(self, output: str = "line one\nline two") -> None:
        self.output = output
        self.calls: list[tuple[str, dict[str, JSON]]] = []

    def call(self, tool: str, params: Mapping[str, JSON]) -> str:
        self.calls.append((tool, dict(params)))
        return self.output


class FakeMemory:
    def __init__(self) -> None:
        self.commits: list[tuple[str, JSON]] = []

    def recall(self, engagement_id: str, scope: JSON) -> JSON:
        return {}

    def commit(self, engagement_id: str, atoms: JSON) -> None:
        self.commits.append((engagement_id, atoms))
