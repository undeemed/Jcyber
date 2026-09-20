"""Shared fixtures. The engagement/scope config is the canonical example from
schema/storage-layout.md, parsed through the real loaders so tests stay
aligned with the docs."""

from __future__ import annotations

import pytest

from jcyber.config import Engagement, scope_from_json
from jcyber.types import JSON, Scope

ENGAGEMENT_JSON: JSON = {
    "target": "acme-lab.example",
    "program": "acme-lab bug bounty",
    "jev": {"model": "jev-latest", "state_budget_chars": 24000},
    "gates": {
        "recon_passive": {"auto": 0.80, "else": "queue"},
        "recon_active": {"auto": 0.85, "else": "queue"},
        "probing": {"auto": 0.90, "else": "confirm"},
        "verify": {"auto": 0.90, "else": "re-decide"},
        "fuzzing": {"auto": 0.95, "else": "confirm"},
        "report": {"auto": 0.95, "else": "confirm"},
        "scope_model_floor": {"auto": 0.90, "else": "queue"},
    },
    "verdicts": {"promote": 0.80, "retire": 0.20},
    "report_ready": 0.95,
    "budget": {"wallclock_hours": 24, "jev_calls": 500, "tool_runs": 300},
    "caido": {"proxy": "127.0.0.1:8889"},
    "engine": {
        "enabled": False,
        "provider": "cerebras",
        "model": "qwen-3.8-27b",
        "model_trivial": "gpt-oss-120b",
    },
}

SCOPE_JSON: JSON = {
    "engagement": "acme-lab",
    "in_scope": [
        {"kind": "host", "value": "acme-lab.example"},
        {"kind": "prefix", "value": "*.acme-lab.example"},
        {"kind": "path", "value": "acme-lab.example/api/", "note": "no /admin (see out)"},
        {"kind": "ip_range", "value": "203.0.113.0/24"},
    ],
    "out_of_scope": [
        {"kind": "host", "value": "staging.acme-lab.example", "note": "no active scanning"},
        {"kind": "path", "value": "acme-lab.example/pay/", "note": "payment: Do Not Test"},
    ],
    "constraints": {
        "rate_limit_rps": 5,
        "time_window": "08:00-20:00 UTC",
        "no_fuzzing_on": ["/checkout", "/pay"],
        "severity": "critical",
        "authorized_accounts": ["jcyber-test1@acme-lab.example", "jcyber-test2@acme-lab.example"],
    },
}


@pytest.fixture
def cfg() -> Engagement:
    return Engagement.from_json(ENGAGEMENT_JSON)


@pytest.fixture
def scope() -> Scope:
    return scope_from_json(SCOPE_JSON)
