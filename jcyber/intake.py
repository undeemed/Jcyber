"""Bare-link intake: synthesize the scope for a target link. The user's new
default: a link with no scope items given means a full scan of the target
(apex host plus every subdomain) with a critical-only findings focus.

Only the scope is synthesized here. The operator still authors
``engagement.toon`` (gates, verdicts, Jev pin, budgets) -- the code holds
no gate values (AGENTS.md invariant #2). The emitted ``scope.toon`` is
always encoder output (invariant #1)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from jcyber.types import JSON

SEVERITY_LEVELS = ("none", "low", "medium", "high", "critical")


@dataclass(frozen=True)
class Intake:
    slug: str
    host: str
    scope_json: JSON


def intake_link(link: str, severity: str = "critical") -> Intake:
    """Resolve a target link (URL, host, or host/path) to an intake.

    ``severity`` must be one of SEVERITY_LEVELS; it defaults to critical --
    the report covers criticals only. A leading ``www.`` is stripped from
    the host (so the scope is anchored at the apex domain) and slug."""
    if severity not in SEVERITY_LEVELS:
        raise ValueError(f"severity must be one of {SEVERITY_LEVELS}")
    u = urlsplit(link if "://" in link else "http://" + link)
    host = (u.hostname or "").lower().removeprefix("www.")
    if not host:
        raise ValueError(f"no host in target: {link!r}")
    slug = host.replace(".", "-")
    return Intake(
        slug=slug,
        host=host,
        scope_json={
            "engagement": slug,
            # full scan: the apex host and every subdomain
            "in_scope": [{"kind": "host", "value": host}, {"kind": "prefix", "value": f"*.{host}"}],
            "out_of_scope": [],
            "constraints": {
                # 5 rps matches the canonical lab example (storage-layout.md)
                "rate_limit_rps": 5,
                "time_window": "",
                "no_fuzzing_on": [],
                "authorized_accounts": [],
                "severity": severity,
            },
        },
    )
