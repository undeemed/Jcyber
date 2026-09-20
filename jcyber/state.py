"""State projector: render the projected engagement graph into the bounded
text state Jev sees. The catalog requires state to be text-only, English-
primary, and <= state_budget_chars (config/decision-catalog.md), so this
always returns a string."""

from __future__ import annotations

import json

from .types import JSON


def build_state(projection: JSON, budget_chars: int) -> str:
    return json.dumps(projection)[:budget_chars]
