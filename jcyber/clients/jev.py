# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Jev observation classifiers — fast atomic gut-checks that accelerate the
agent's work. Two tools: suggest severity, check duplicates.

Benchmarked at 8.7x faster than agent completion for these classification
tasks (severity avg 0.24s, duplicate avg 0.17s vs agent 1.46s, 2.08s).

These are optional accelerators the agent can call or ignore. The agent
harness remains the reasoning and decision layer.

Requires TYPESAFE_API_KEY in the environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import typesafe_sdk as ts


@dataclass(frozen=True)
class SeverityResult:
    severity: str  # none | low | medium | high | critical
    score: float  # 0-4 weighted index
    confidence: float


@dataclass(frozen=True)
class DuplicateResult:
    duplicate_probability: float  # P(yes), 0-1


class JevClassifier:
    """Thin wrapper over TypeSafe system_one for observation classification."""

    def __init__(self, client: ts.TypeSafeClient) -> None:
        self._client = client

    @classmethod
    def from_env(cls) -> JevClassifier:
        return cls(ts.TypeSafeClient())

    def severity(self, title: str, evidence_summary: str) -> SeverityResult:
        """Score severity for a finding based on title and evidence."""
        state = f"Finding: {title}\nEvidence: {evidence_summary}"
        resp = self._client.system_one(
            state,
            {
                "severity": ts.Score(
                    instructions=(
                        "Rate the security severity of this finding. Consider: "
                        "attack complexity, required privileges, user interaction, "
                        "confidentiality/integrity/availability impact."
                    ),
                    criteria=["none", "low", "medium", "high", "critical"],
                ),
            },
        )
        ans = cast(ts.ScoreAnswer, resp.answers["severity"])
        sev_map = {0: "none", 1: "low", 2: "medium", 3: "high", 4: "critical"}
        return SeverityResult(
            severity=sev_map.get(round(ans.score), "unknown"),
            score=ans.score,
            confidence=ans.confidence,
        )

    def check_duplicate(self, new_summary: str, existing_summaries: list[str]) -> DuplicateResult:
        """Check if new evidence is substantially similar to existing evidence."""
        existing = "\n".join(f"- {s}" for s in existing_summaries[:10])
        state = f"New evidence: {new_summary}\n\nExisting evidence:\n{existing}"
        resp = self._client.system_one(
            state,
            {
                "is_duplicate": ts.Noul(
                    instructions=(
                        "Is the new evidence substantially the same finding as any of the "
                        "existing evidence items? Answer yes if it reports the same "
                        "vulnerability or issue on the same target, even with different "
                        "wording. Answer no if it is a genuinely new finding."
                    ),
                ),
            },
        )
        ans = cast(ts.NoulAnswer, resp.answers["is_duplicate"])
        return DuplicateResult(duplicate_probability=ans.noul)
