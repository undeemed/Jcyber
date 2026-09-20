"""Decision trace renderer: readable audit lines from the :Decision log. Auto
decisions show their confidences; non-auto decisions also surface the reason."""

from __future__ import annotations

from jcyber.trace import render
from jcyber.types import JSON


def test_empty_trace() -> None:
    md = render("acme-lab", [])
    assert "# Jcyber trace: acme-lab" in md
    assert "0 decision(s)" in md


def test_trace_lines_show_action_outcome_and_confidences() -> None:
    decisions: list[JSON] = [
        {
            "ts": "t1",
            "target": "127.0.0.1",
            "action": "recon_active",
            "outcome": "auto",
            "next_action_conf": 0.97,
            "scope_safe": 0.96,
            "report_ready": 0.1,
            "reason": "auto",
        },
        {
            "ts": "t2",
            "target": "10.0.0.1",
            "action": "recon_active",
            "outcome": "blocked",
            "next_action_conf": 0.9,
            "scope_safe": 0.9,
            "report_ready": 0.1,
            "reason": "deterministic out-of-scope",
        },
    ]
    md = render("acme-lab", decisions)
    assert "2 decision(s)" in md
    assert "conf=0.97 scope=0.96" in md
    # non-auto decision surfaces its reason; the auto one does not
    assert "reason: deterministic out-of-scope" in md
    assert md.count("reason:") == 1
