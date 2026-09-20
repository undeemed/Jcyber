"""Shared fixtures. The engagement/scope config matches the stripped
Engagement shape (target, program, budget, caido proxy)."""

from __future__ import annotations

import pytest

from jcyber.config import Engagement, scope_from_json
from jcyber.types import JSON, Scope

ENGAGEMENT_JSON: JSON = {
    "target": "acme-lab.example",
    "program": "acme-lab bug bounty",
    "budget": {"wallclock_hours": 24, "tool_runs": 300},
    "caido": {"proxy": "127.0.0.1:8889"},
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
