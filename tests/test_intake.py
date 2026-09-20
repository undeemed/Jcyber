"""Bare-link intake: full scan (apex + subdomains) + critical-only is the
default. Contracts are tested through the real gate and the real scope
parser -- not by asserting on the JSON shape."""

from __future__ import annotations

import pytest

from jcyber.config import scope_from_json
from jcyber.intake import SEVERITY_LEVELS, intake_link
from jcyber.scope import in_scope

LINK = "https://www.acme-lab.example/docs"


def test_default_scope_covers_apex_and_subdomains() -> None:
    scope = scope_from_json(intake_link(LINK).scope_json)
    assert in_scope("https://acme-lab.example/", scope)
    assert in_scope("https://deep.sub.acme-lab.example/x", scope)
    assert not in_scope("https://other.example/", scope)


def test_slug_and_host_strip_www() -> None:
    intake = intake_link(LINK)
    assert intake.slug == "acme-lab-example"
    assert intake.host == "acme-lab.example"
    scope = scope_from_json(intake.scope_json)
    assert scope.engagement == "acme-lab-example"
    assert in_scope("https://acme-lab.example/", scope)  # apex in scope
    assert in_scope("https://api.acme-lab.example/x", scope)  # sibling subdomain


def test_severity_defaults_critical_and_overrides() -> None:
    assert scope_from_json(intake_link(LINK).scope_json).severity_focus.value == "critical"
    for level in SEVERITY_LEVELS:
        assert scope_from_json(intake_link(LINK, level).scope_json).severity_focus.value == level


@pytest.mark.parametrize("bad", ["urgent", "HIGH", ""])
def test_bad_severity_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        intake_link(LINK, bad)


def test_host_only_input() -> None:
    intake = intake_link("acme-lab.example")
    assert intake.host == "acme-lab.example"
    scope = scope_from_json(intake.scope_json)
    assert in_scope("https://acme-lab.example/pay", scope)  # carve-outs unset
