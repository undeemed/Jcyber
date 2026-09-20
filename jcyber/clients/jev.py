# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Jev observation classifiers — fast atomic gut-checks that accelerate the
agent's work. Four tools: triage evidence, suggest severity, check duplicates,
suggest next tool category.

These are optional accelerators the agent can call or ignore. The agent
harness remains the reasoning and decision layer — Jev provides fast typed
classifications so the agent spends tokens on reasoning about attack chains,
not pattern-matching tool output.

Requires TYPESAFE_API_KEY in the environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import typesafe_sdk as ts

# Tool categories for suggest_tool_category — grouped by phase.
# The agent picks the specific tool; Jev only suggests the category.
TOOL_CATEGORIES: dict[str, str] = {
    "recon_passive": "Passive recon: subdomain enum, URL discovery, WAF detection",
    "recon_active": "Active recon: port scan, crawling, directory brute-force",
    "probing": "Vulnerability probing: nuclei templates, SQLi, XSS, API audit",
    "fuzzing": "Fuzzing: parameter, directory, header fuzzing",
    "verify": "Verification: replay requests, confirm findings with second tool",
}


@dataclass(frozen=True)
class TriageResult:
    vuln_probability: float  # P(yes), 0-1


@dataclass(frozen=True)
class SeverityResult:
    severity: str  # none | low | medium | high | critical
    score: float  # 0-4 weighted index
    confidence: float


@dataclass(frozen=True)
class DuplicateResult:
    duplicate_probability: float  # P(yes), 0-1


@dataclass(frozen=True)
class ToolHint:
    category: str  # one of TOOL_CATEGORIES keys
    confidence: float
    probabilities: dict[str, float]


class JevClassifier:
    """Thin wrapper over TypeSafe system_one for observation classification."""

    def __init__(self, client: ts.TypeSafeClient) -> None:
        self._client = client

    @classmethod
    def from_env(cls) -> JevClassifier:
        return cls(ts.TypeSafeClient())

    def triage(self, tool: str, target: str, summary: str) -> TriageResult:
        """Classify whether evidence output indicates a vulnerability."""
        state = f"Tool: {tool}\nTarget: {target}\nOutput summary: {summary}"
        resp = self._client.system_one(
            state,
            {
                "vuln_indicator": ts.Noul(
                    instructions=(
                        "Does this tool output indicate a potential security vulnerability, "
                        "misconfiguration, or information disclosure? Answer yes if there is "
                        "any security-relevant finding, even minor. Answer no for clean scans "
                        "with no findings."
                    ),
                ),
            },
        )
        ans = cast(ts.NoulAnswer, resp.answers["vuln_indicator"])
        return TriageResult(vuln_probability=ans.noul)

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

    def suggest_tool_category(self, state_summary: str) -> ToolHint:
        """Suggest which tool category to run next, given the engagement state.

        This is an ignorable hint — a ranked suggestion the agent can take or
        skip. It never gates execution or enters the control path.
        """
        resp = self._client.system_one(
            state_summary,
            {
                "next_category": ts.Choice(
                    instructions=(
                        "Given the current engagement state, which category of tool "
                        "would be most productive to run next? Consider what has already "
                        "been scanned, what evidence exists, and what gaps remain."
                    ),
                    criteria=dict(TOOL_CATEGORIES),
                ),
            },
        )
        ans = cast(ts.ChoiceAnswer, resp.answers["next_category"])
        return ToolHint(
            category=ans.choice,
            confidence=ans.confidence,
            probabilities={str(k): float(v) for k, v in ans.probabilities.items()},
        )
