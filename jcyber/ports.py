"""Ports — the seams the MCP server depends on. Every external system
implements one of these Protocols, so the server is driven through
interfaces and faked in tests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from .types import JSON, Evidence


class ToonCodec(Protocol):
    def encode(self, obj: JSON) -> str: ...
    def decode(self, text: str) -> JSON: ...


class GraphStore(Protocol):
    """Memgraph session brain."""

    def project_state(self, engagement_id: str) -> JSON: ...
    def report_data(self, engagement_id: str) -> JSON: ...
    def write_decision(self, engagement_id: str, record: JSON) -> None: ...
    def decision_log(self, engagement_id: str) -> list[JSON]: ...
    def insert_evidence(self, ev: Evidence) -> None: ...
    def seen_sha256(self, engagement_id: str, sha256: str) -> bool: ...
    def apply_verdict(
        self, engagement_id: str, hypothesis_id: str, verdict: str, support: float
    ) -> None: ...
    def create_hypothesis(
        self, engagement_id: str, hid: str, text: str, evidence_id: str
    ) -> None: ...
    def create_finding(
        self, engagement_id: str, fid: str, title: str, hypothesis_id: str
    ) -> None: ...
    def score_finding(self, engagement_id: str, fid: str, severity: int) -> None: ...


class Hands(Protocol):
    """HexStrike. One call = (closed-set tool name, closed-set params)."""

    def call(self, tool: str, params: Mapping[str, JSON]) -> str: ...


class Proxy(Protocol):
    """Caido. Passive substrate: its plugin verdicts enter as evidence, never
    as decisions."""

    def findings(self, engagement_id: str) -> list[JSON]: ...


class Memory(Protocol):
    """TencentDB long-term brain. Read at recall, written at commit — the only
    two touch points, never in the hot path."""

    def recall(self, engagement_id: str, scope: JSON) -> JSON: ...
    def commit(self, engagement_id: str, atoms: JSON) -> None: ...
