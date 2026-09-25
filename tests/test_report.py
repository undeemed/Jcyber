"""Report renderer: deterministic Markdown from graph report_data. Each
validated finding is rendered with its linked evidence; an empty graph renders
the no-findings line."""

from __future__ import annotations

from jcyber.report import render
from jcyber.types import JSON


def test_empty_graph_renders_no_findings() -> None:
    md = render({"engagement": "acme-lab", "findings": []})
    assert "# Jcyber report: acme-lab" in md
    assert "No validated findings." in md


def test_findings_render_with_linked_evidence() -> None:
    data: JSON = {
        "engagement": "acme-lab",
        "findings": [
            {
                "id": "VF-001",
                "title": "IDOR on /api/invoice",
                "severity": 4,
                "justification": "sequential id, cross-account read",
                "evidence": [
                    {"id": "E-007", "tool": "caido/autorize", "summary": "200 for other account"},
                    {"id": "E-004", "tool": "ffuf_scan", "summary": "id param enumerable"},
                ],
            }
        ],
    }
    md = render(data)
    assert "## VF-001 - IDOR on /api/invoice" in md
    assert "severity: 4" in md
    assert "E-007 [caido/autorize] 200 for other account" in md
    assert "E-004 [ffuf_scan] id param enumerable" in md


def test_render_is_deterministic() -> None:
    data: JSON = {"engagement": "x", "findings": [{"id": "VF-001", "title": "t", "severity": 3}]}
    assert render(data) == render(data)


def test_evidence_and_findings_sorted_by_id() -> None:
    # report_data (live Cypher collect) returns evidence unordered; render must
    # sort by id so the Markdown is byte-deterministic run to run.
    data: JSON = {
        "engagement": "x",
        "findings": [
            {"id": "VF-002", "title": "b", "severity": 3, "evidence": []},
            {
                "id": "VF-001",
                "title": "a",
                "severity": 4,
                "evidence": [
                    {"id": "E-009", "tool": "ffuf", "summary": "late"},
                    {"id": "E-002", "tool": "nuclei", "summary": "early"},
                ],
            },
        ],
    }
    md = render(data)
    assert md.index("VF-001") < md.index("VF-002")  # findings by id
    assert md.index("E-002") < md.index("E-009")  # evidence by id


def test_attack_chains_rendered_before_findings() -> None:
    data: JSON = {
        "engagement": "acme-lab",
        "findings": [{"id": "VF-001", "title": "SQLi", "severity": 4}],
        "attack_chains": [
            {
                "id": "AC-001",
                "title": "Debug to DB dump",
                "impact": "Full database access",
                "status": "demonstrated",
                "steps": [
                    {"n": 1, "id": "F-001", "label": "Finding", "title": "Debug param"},
                    {"n": 2, "id": "F-002", "label": "Finding", "title": "DB dump"},
                ],
            }
        ],
    }
    md = render(data)
    assert "## Attack Chains (1)" in md
    assert "### AC-001 - Debug to DB dump" in md
    assert "impact: Full database access" in md
    assert md.index("AC-001") < md.index("VF-001")


def test_report_no_chains_key() -> None:
    """Backward compat: report_data without attack_chains key still works."""
    data: JSON = {
        "engagement": "x",
        "findings": [{"id": "VF-001", "title": "t", "severity": 3}],
    }
    md = render(data)
    assert "VF-001" in md
    assert "Attack Chains" not in md
