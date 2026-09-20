"""Deterministic scope gate -- the non-jailbreakable layer 1. These are safety
tests: out-of-scope must win every conflict."""

from __future__ import annotations

from jcyber.scope import in_scope, violates_no_fuzzing
from jcyber.types import Scope


def test_in_scope_host_and_path(scope: Scope) -> None:
    assert in_scope("https://acme-lab.example/api/users/4821", scope)


def test_subdomain_prefix_in_scope(scope: Scope) -> None:
    assert in_scope("https://sub.acme-lab.example/", scope)


def test_ip_range_in_scope(scope: Scope) -> None:
    assert in_scope("http://203.0.113.5/", scope)


def test_out_of_scope_host_wins_over_prefix(scope: Scope) -> None:
    # staging.acme-lab.example matches the *.acme-lab.example prefix but is
    # explicitly out of scope -- out-of-scope must win.
    assert not in_scope("https://staging.acme-lab.example/x", scope)


def test_out_of_scope_path_wins(scope: Scope) -> None:
    assert not in_scope("https://acme-lab.example/pay/checkout", scope)


def test_unknown_host_not_in_scope(scope: Scope) -> None:
    assert not in_scope("https://evil.example/", scope)


def test_empty_target_not_in_scope(scope: Scope) -> None:
    assert not in_scope("", scope)


def test_no_fuzzing_paths(scope: Scope) -> None:
    assert violates_no_fuzzing("https://acme-lab.example/checkout/cart", scope)
    assert not violates_no_fuzzing("https://acme-lab.example/api/users", scope)


def test_out_of_scope_path_blocks_case_and_slash_variants(scope: Scope) -> None:
    # The /pay/ carve-out must hold against no-trailing-slash and case variants.
    assert not in_scope("https://acme-lab.example/pay", scope)
    assert not in_scope("https://acme-lab.example/pay/", scope)
    assert not in_scope("https://acme-lab.example/PAY/checkout", scope)


def test_sibling_path_not_over_blocked(scope: Scope) -> None:
    # /payments is a distinct segment, not covered by the /pay/ carve-out.
    assert in_scope("https://acme-lab.example/payments", scope)
