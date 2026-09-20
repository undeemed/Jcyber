"""Distiller: scan the projection for durable atoms (validated findings,
retired hypotheses) and commit them to the long-term brain. Written at commit
only -- never in the hot path. (Skill extraction from working bypasses is
deferred to live wiring.)"""

from __future__ import annotations

from .ports import Memory
from .types import JSON


def distill(projection: JSON) -> JSON:
    atoms: dict[str, JSON] = {"validated_findings": [], "retired_hypotheses": []}
    if isinstance(projection, dict):
        vf = projection.get("validated_findings")
        if isinstance(vf, list):
            atoms["validated_findings"] = vf
        rh = projection.get("retired_hypotheses")
        if isinstance(rh, list):
            atoms["retired_hypotheses"] = rh
    return atoms


def commit_learnings(memory: Memory, engagement_id: str, projection: JSON) -> None:
    memory.commit(engagement_id, distill(projection))
