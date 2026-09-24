# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportPrivateUsage=false
"""MCP tool-level tests: exercise every management tool function through the
server state + fakes. Each tool is called directly (not via MCP transport)
so we test business logic and annotations without needing live backends."""

from __future__ import annotations

import json

import pytest

import jcyber.mcp_server as _mod
from jcyber.clients.jev import DuplicateResult, SeverityResult
from jcyber.mcp_server import (
    _state,
    check_duplicate,
    commit_learnings,
    create_hypothesis,
    get_decision_trace,
    get_state,
    intake_target,
    mcp,
    promote_finding,
    recall_lessons,
    render_findings_report,
    retire_hypothesis,
    score_finding,
    suggest_severity,
)
from tests.fakes import FakeGraph, FakeHands, FakeMemory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset server state before each test."""
    old_graph = _state.graph
    old_hands = _state.hands
    old_memory = _state.memory
    old_cfg = _state.cfg
    old_scope = _state.scope
    old_eid = _state.engagement_id
    old_e = _state._ev_seq
    old_h = _state._h_seq
    old_f = _state._f_seq
    old_bc = _mod._backends_connected

    yield

    _state.graph = old_graph
    _state.hands = old_hands
    _state.memory = old_memory
    _state.cfg = old_cfg
    _state.scope = old_scope
    _state.engagement_id = old_eid
    _state._ev_seq = old_e
    _state._h_seq = old_h
    _state._f_seq = old_f
    _mod._backends_connected = old_bc


def _wire_fakes(
    graph: FakeGraph | None = None,
    hands: FakeHands | None = None,
    memory: FakeMemory | None = None,
) -> None:
    # Prevent _ensure_backends from trying real connections
    _mod._backends_connected = True
    _state.graph = graph or FakeGraph()  # type: ignore[assignment]
    _state.hands = hands or FakeHands()  # type: ignore[assignment]
    _state.memory = memory or FakeMemory()  # type: ignore[assignment]
    _state.engagement_id = "test-eng"
    _state._ev_seq = 0
    _state._h_seq = 0
    _state._f_seq = 0


# ---------------------------------------------------------------------------
# Annotation tests — every tool has all four hints set to explicit booleans
# ---------------------------------------------------------------------------


def test_all_tools_have_annotations():
    """Every registered tool has readOnlyHint, destructiveHint,
    idempotentHint, and openWorldHint set to explicit booleans."""
    tools = mcp._tool_manager.list_tools()
    assert len(tools) > 0, "no tools registered"
    for tool in tools:
        ann = tool.annotations
        assert ann is not None, f"{tool.name}: missing annotations"
        assert isinstance(ann.read_only_hint, bool), f"{tool.name}: readOnlyHint not bool"
        assert isinstance(ann.destructive_hint, bool), f"{tool.name}: destructiveHint not bool"
        assert isinstance(ann.idempotent_hint, bool), f"{tool.name}: idempotentHint not bool"
        assert isinstance(ann.open_world_hint, bool), f"{tool.name}: openWorldHint not bool"


def test_exploit_tools_marked_destructive():
    """Exploit tools that require operator confirmation are marked destructive."""
    from jcyber.mcp_server import EXPLOIT_TOOLS

    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    for name in EXPLOIT_TOOLS:
        assert name in tools, f"exploit tool {name} not registered"
        assert tools[name].annotations.destructive_hint is True, f"{name} should be destructive"


def test_readonly_tools_not_destructive():
    """Read-only tools must not also be destructive."""
    for tool in mcp._tool_manager.list_tools():
        if tool.annotations and tool.annotations.read_only_hint:
            assert not tool.annotations.destructive_hint, (
                f"{tool.name}: read-only but also destructive"
            )


# ---------------------------------------------------------------------------
# Management tools — each tool referenced by name, exercised through fakes
# ---------------------------------------------------------------------------


def test_get_state():
    _wire_fakes()
    result = json.loads(get_state())
    assert "phase" in result


def test_render_findings_report():
    _wire_fakes(graph=FakeGraph(report={"engagement": "test-eng", "findings": []}))
    md = render_findings_report()
    assert "test-eng" in md


def test_get_decision_trace():
    graph = FakeGraph()
    graph.decisions = [
        {
            "ts": "t1",
            "target": "x",
            "action": "recon_active",
            "outcome": "auto",
            "next_action_conf": 0.9,
            "scope_safe": 0.9,
            "report_ready": 0.1,
            "reason": "auto",
        }
    ]
    _wire_fakes(graph=graph)
    md = get_decision_trace()
    assert "1 decision(s)" in md


def test_create_hypothesis():
    _wire_fakes()
    result = json.loads(create_hypothesis("sqli in /api/search", "E-001"))
    assert result["hypothesis_id"] == "H-001"
    assert result["evidence_id"] == "E-001"


def test_promote_finding():
    _wire_fakes()
    result = json.loads(promote_finding("H-001", "IDOR on /api/invoice"))
    assert result["finding_id"] == "F-001"
    assert result["from_hypothesis"] == "H-001"


def test_score_finding():
    _wire_fakes()
    result = json.loads(score_finding("F-001", "critical"))
    assert result["severity"] == "critical"
    assert result["status"] == "validated"


def test_score_finding_invalid_severity():
    _wire_fakes()
    with pytest.raises(ValueError, match="severity must be one of"):
        score_finding("F-001", "urgent")


def test_retire_hypothesis():
    _wire_fakes()
    result = json.loads(retire_hypothesis("H-001", "not exploitable"))
    assert result["status"] == "retired"
    assert result["reason"] == "not exploitable"


def test_recall_lessons_no_memory():
    _wire_fakes()
    _state.memory = None
    result = json.loads(recall_lessons("WordPress"))
    assert result["status"] == "no_memory"


def test_recall_lessons_with_memory():
    _wire_fakes(memory=FakeMemory(priors={"lessons": ["use wpscan"]}))
    result = json.loads(recall_lessons("WordPress"))
    assert result["lessons"] == ["use wpscan"]


def test_commit_learnings_no_memory():
    _wire_fakes()
    _state.memory = None
    result = json.loads(commit_learnings())
    assert result["status"] == "no_memory"


def test_commit_learnings_with_memory():
    _wire_fakes(memory=FakeMemory())
    result = json.loads(commit_learnings())
    assert result["status"] == "committed"


# ---------------------------------------------------------------------------
# intake_target — needs _ensure_backends bypass, no graph
# ---------------------------------------------------------------------------


def test_intake_target():
    _wire_fakes()
    _state.graph = None  # skip bootstrap_engagement
    result = json.loads(intake_target("https://acme-lab.example/docs"))
    assert result["engagement_id"] == "acme-lab-example"
    assert result["target"] == "acme-lab.example"
    assert result["status"] == "active"


# ---------------------------------------------------------------------------
# Jev classifier tools — monkeypatch _get_jev
# ---------------------------------------------------------------------------


class _FakeJev:
    """Minimal stand-in for JevClassifier."""

    def severity(self, title: str, evidence_summary: str) -> SeverityResult:
        return SeverityResult(severity="high", score=3.0, confidence=0.95)

    def check_duplicate(self, new_summary: str, existing_summaries: list[str]) -> DuplicateResult:
        return DuplicateResult(duplicate_probability=0.85)


def test_suggest_severity(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_fakes()
    monkeypatch.setattr(_mod, "_jev", _FakeJev())
    result = json.loads(suggest_severity("F-001", "XSS in search", "reflected input"))
    assert result["suggested_severity"] == "high"
    assert result["finding_id"] == "F-001"


def test_check_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_fakes(
        graph=FakeGraph(
            projection={
                "phase": "recon",
                "open_hypotheses": [],
                "validated_findings": [],
                "recent_evidence": [{"summary": "port 22 open"}],
                "tools_run": [],
                "unscored_findings": [],
            }
        )
    )
    monkeypatch.setattr(_mod, "_jev", _FakeJev())
    result = json.loads(check_duplicate("port 22 open on target"))
    assert result["is_duplicate"] is True
    assert result["compared_against"] == 1


# ---------------------------------------------------------------------------
# Parametrized: every HexStrike tool registered with annotations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", list(_mod.TOOL_CATALOG))
def test_hexstrike_tool_registered_with_annotations(tool_name: str) -> None:
    """Each HexStrike tool from TOOL_CATALOG is registered and annotated."""
    tool = mcp._tool_manager.get_tool(tool_name)
    assert tool is not None, f"{tool_name} not registered"
    ann = tool.annotations
    assert ann is not None, f"{tool_name}: missing annotations"
    assert isinstance(ann.read_only_hint, bool)
    assert isinstance(ann.destructive_hint, bool)
    assert isinstance(ann.idempotent_hint, bool)
    assert isinstance(ann.open_world_hint, bool)
