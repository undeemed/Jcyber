"""Core domain types. Pure data — no I/O, no SDK imports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

type JSON = str | int | float | bool | None | dict[str, JSON] | list[JSON]


class ActionClass(StrEnum):
    recon_passive = "recon_passive"
    recon_active = "recon_active"
    probing = "probing"
    fuzzing = "fuzzing"
    verify = "verify"
    exploit = "exploit"
    report = "report"
    commit = "commit"


class Outcome(StrEnum):
    auto = "auto"
    confirm_parked = "confirm_parked"
    blocked = "blocked"
    halted = "halted"


# --- Jev question representation (adapter-agnostic; no typesafe types leak here) ---
@dataclass(frozen=True)
class NoulQ:
    instructions: str


@dataclass(frozen=True)
class ChoiceQ:
    instructions: str
    options: dict[str, str]


@dataclass(frozen=True)
class ScoreQ:
    instructions: str
    levels: list[str]


type Question = NoulQ | ChoiceQ | ScoreQ


# --- Jev typed answers (projected from the SDK response) ---
@dataclass(frozen=True)
class NoulAns:
    noul: float  # P(yes)


@dataclass(frozen=True)
class ChoiceAns:
    choice: str
    confidence: float
    probabilities: dict[str, float]


@dataclass(frozen=True)
class ScoreAns:
    score: float
    confidence: float
    probabilities: dict[int, float]


type Answer = NoulAns | ChoiceAns | ScoreAns


@dataclass(frozen=True)
class Decision:
    """The typed Jev answers for one iteration, projected for the loop."""

    next_action: ChoiceAns
    scope_safe: NoulAns
    report_ready: NoulAns
    supports: dict[str, NoulAns]
    skill_pick: ChoiceAns | None = None
    route_via_engine: ChoiceAns | None = None


@dataclass(frozen=True)
class ToolCall:
    tool: str
    params: dict[str, JSON]


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
class GateResult:
    outcome: Outcome
    action_class: ActionClass
    reason: str


@dataclass(frozen=True)
class ScopeItem:
    kind: str  # host | prefix | path | ip_range
    value: str
    note: str | None = None


class Severity(StrEnum):
    """Report-triage floor, G3 legend (config/decision-catalog.md):
    none=0, low=1, medium=2, high=3, critical=4. The report keeps
    findings whose stored severity score is >= this level's score
    (default critical -> only 4). Never a gate input."""

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
    severity_focus: Severity = Severity.critical  # report triage level; default critical-only
