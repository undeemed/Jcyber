"""Report renderer: deterministic Markdown from the graph's validated findings
plus their linked evidence. Pure function of GraphStore.report_data output; no
I/O, no model. The report is rendered from the graph, never hand-written
(PLAN.md section 4.8)."""

from __future__ import annotations

from .types import JSON


def render(data: JSON) -> str:
    engagement = ""
    findings: list[dict[str, JSON]] = []
    if isinstance(data, dict):
        eng = data.get("engagement")
        if isinstance(eng, str):
            engagement = eng
        raw = data.get("findings")
        if isinstance(raw, list):
            findings = sorted(
                (f for f in raw if isinstance(f, dict)), key=lambda f: str(f.get("id", ""))
            )

    lines = [f"# Jcyber report: {engagement}", ""]
    if not findings:
        lines.append("No validated findings.")
        return "\n".join(lines) + "\n"

    lines.append(f"{len(findings)} validated finding(s), by id:")
    lines.append("")
    for f in findings:
        heading = f"## {f.get('id', 'VF-?')} - {f.get('title', '')}".rstrip(" -")
        lines.append(heading)
        lines.append(f"- severity: {f.get('severity', '')}")
        justification = f.get("justification")
        if justification:
            lines.append(f"- justification: {justification}")
        evidence: list[dict[str, JSON]] = []
        raw_ev = f.get("evidence")
        if isinstance(raw_ev, list):
            evidence = sorted(
                (e for e in raw_ev if isinstance(e, dict)), key=lambda e: str(e.get("id", ""))
            )
        lines.append(f"- evidence ({len(evidence)}):")
        for e in evidence:
            lines.append(f"  - {e.get('id', 'E-?')} [{e.get('tool', '')}] {e.get('summary', '')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
