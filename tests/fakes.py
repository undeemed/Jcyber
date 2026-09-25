"""In-memory fakes for the ports. Tests use these instead of real backends."""

from __future__ import annotations

from collections.abc import Mapping

from jcyber.types import JSON, Evidence


class FakeGraph:
    def __init__(self, projection: JSON | None = None, report: JSON | None = None) -> None:
        self.projection: JSON = (
            projection
            if projection is not None
            else {
                "phase": "recon",
                "open_hypotheses": [],
                "validated_findings": [],
                "recent_evidence": [],
                "tools_run": [],
                "unscored_findings": [],
                "attack_chains": [],
            }
        )
        self.decisions: list[JSON] = []
        self.evidence: list[Evidence] = []
        self.verdicts: list[tuple[str, str, float]] = []
        self._seen: set[str] = set()
        self.report: JSON = report if report is not None else {"engagement": "", "findings": []}
        self.chains: list[dict[str, JSON]] = []

    def project_state(self, engagement_id: str) -> JSON:
        return self.projection

    def report_data(self, engagement_id: str) -> JSON:
        return self.report

    def write_decision(self, engagement_id: str, record: JSON) -> None:
        self.decisions.append(record)

    def decision_log(self, engagement_id: str) -> list[JSON]:
        return list(self.decisions)

    def insert_evidence(self, ev: Evidence) -> None:
        self.evidence.append(ev)
        self._seen.add(ev.sha256)

    def seen_sha256(self, engagement_id: str, sha256: str) -> bool:
        return sha256 in self._seen

    def apply_verdict(
        self, engagement_id: str, hypothesis_id: str, verdict: str, support: float
    ) -> None:
        self.verdicts.append((hypothesis_id, verdict, support))

    def create_hypothesis(self, engagement_id: str, hid: str, text: str, evidence_id: str) -> None:
        pass

    def create_finding(self, engagement_id: str, fid: str, title: str, hypothesis_id: str) -> None:
        pass

    def score_finding(self, engagement_id: str, fid: str, severity: int) -> None:
        pass

    def create_attack_chain(
        self, engagement_id: str, ac_id: str, title: str, impact: str, step_ids: list[str]
    ) -> str:
        status = "demonstrated" if all(s.startswith("F-") for s in step_ids) else "theoretical"
        steps: list[JSON] = list(step_ids)
        self.chains.append(
            {"id": ac_id, "title": title, "impact": impact, "status": status, "steps": steps}
        )
        return status

    def get_attack_chains(self, engagement_id: str) -> list[JSON]:
        return list(self.chains)

    def attack_chain_count(self, engagement_id: str) -> int:
        return len(self.chains)


class FakeHands:
    def __init__(self, output: str = "line one\nline two") -> None:
        self.output = output
        self.calls: list[tuple[str, dict[str, JSON]]] = []

    def call(self, tool: str, params: Mapping[str, JSON]) -> str:
        self.calls.append((tool, dict(params)))
        return self.output


class FakeMemory:
    def __init__(self, priors: JSON | None = None) -> None:
        self.priors = priors
        self.commits: list[tuple[str, JSON]] = []

    def recall(self, engagement_id: str, scope: JSON) -> JSON:
        return self.priors

    def commit(self, engagement_id: str, atoms: JSON) -> None:
        self.commits.append((engagement_id, atoms))


class FakeProxy:
    def __init__(self, findings: list[JSON] | None = None) -> None:
        self._findings = findings or []

    def findings(self, engagement_id: str) -> list[JSON]:
        return list(self._findings)
