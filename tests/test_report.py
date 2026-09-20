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
