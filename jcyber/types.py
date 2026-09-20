"""Core domain types. Pure data — no I/O, no SDK imports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

type JSON = str | int | float | bool | None | dict[str, JSON] | list[JSON]


@dataclass(frozen=True)
class Evidence:
    engagement_id: str
    id: str
    tool: str
    target: str
    ts: str
    summary: str
    sha256: str
    raw_path: str


@dataclass(frozen=True)
class ScopeItem:
    kind: str  # host | prefix | path | ip_range
    value: str
    note: str | None = None


class Severity(StrEnum):
    """Report-triage floor: none=0, low=1, medium=2, high=3, critical=4.
    The report keeps findings whose severity >= this level's score."""

    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    none = "none"

    @property
    def score(self) -> int:
        return {
            Severity.critical: 4,
            Severity.high: 3,
            Severity.medium: 2,
            Severity.low: 1,
            Severity.none: 0,
        }[self]


@dataclass(frozen=True)
class Scope:
    engagement: str
    in_scope: list[ScopeItem]
    out_of_scope: list[ScopeItem]
    no_fuzzing_on: list[str]
    authorized_accounts: list[str]
    rate_limit_rps: int = 0
    time_window: str = ""
    severity_focus: Severity = Severity.critical
