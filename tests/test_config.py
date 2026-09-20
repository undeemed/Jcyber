"""Config parsing from the canonical engagement JSON."""

from __future__ import annotations

from pytest import raises

from jcyber.config import Engagement, scope_from_json
from jcyber.types import JSON, Severity
from tests.conftest import ENGAGEMENT_JSON, SCOPE_JSON


def test_engagement_parses_core_fields() -> None:
    cfg = Engagement.from_json(ENGAGEMENT_JSON)
    assert cfg.target == "acme-lab.example"
    assert cfg.program == "acme-lab bug bounty"
    assert cfg.caido_proxy == "127.0.0.1:8889"
    assert cfg.budget["tool_runs"] == 300


def test_scope_parses_lists() -> None:
    s = scope_from_json(SCOPE_JSON)
    assert len(s.in_scope) == 4
    assert len(s.out_of_scope) == 2
    assert s.no_fuzzing_on == ["/checkout", "/pay"]
    assert s.rate_limit_rps == 5
    assert len(s.authorized_accounts) == 2


def test_severity_scores_match_legend() -> None:
    s = scope_from_json(SCOPE_JSON)
    assert s.severity_focus is Severity.critical
    assert [lv.score for lv in Severity] == [4, 3, 2, 1, 0]


def _scope_doc(severity: str | None) -> JSON:
    c: dict[str, JSON] = {
        "rate_limit_rps": 0,
        "time_window": "",
        "no_fuzzing_on": [],
        "authorized_accounts": [],
    }
    if severity is not None:
        c["severity"] = severity
    return {
        "engagement": "probe",
        "in_scope": [],
        "out_of_scope": [],
        "constraints": c,
    }


def test_severity_focus_default_and_rejection() -> None:
    assert scope_from_json(_scope_doc(None)).severity_focus is Severity.critical
    with raises(ValueError, match="illegal severity_focus"):
        scope_from_json(_scope_doc("bogus"))
