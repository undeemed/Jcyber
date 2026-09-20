"""The decision gate: two scope layers, exploit-never-auto, per-class
confidence, commit-terminal. These pin the safety precedence."""

from __future__ import annotations

from jcyber.config import Engagement
from jcyber.gate import evaluate
from jcyber.types import ActionClass, ChoiceAns, Decision, NoulAns, Outcome, Scope

IN = "https://acme-lab.example/api/users/4821"


def _decision(
    action: str, conf: float, scope_safe: float = 0.99, report_ready: float = 0.20
) -> Decision:
    return Decision(
        next_action=ChoiceAns(choice=action, confidence=conf, probabilities={action: conf}),
        scope_safe=NoulAns(noul=scope_safe),
        report_ready=NoulAns(noul=report_ready),
        supports={},
    )


def test_auto_when_probing_above_threshold(cfg: Engagement, scope: Scope) -> None:
    r = evaluate(IN, _decision("probing", 0.93), cfg, scope)
    assert r.outcome is Outcome.auto
    assert r.action_class is ActionClass.probing


def test_probing_below_threshold_parks(cfg: Engagement, scope: Scope) -> None:
    assert evaluate(IN, _decision("probing", 0.80), cfg, scope).outcome is Outcome.confirm_parked


def test_recon_passive_auto_at_exact_floor(cfg: Engagement, scope: Scope) -> None:
    assert evaluate(IN, _decision("recon_passive", 0.80), cfg, scope).outcome is Outcome.auto
    below = evaluate(IN, _decision("recon_passive", 0.79), cfg, scope)
    assert below.outcome is Outcome.confirm_parked


def test_scope_safe_below_floor_parks(cfg: Engagement, scope: Scope) -> None:
    r = evaluate(IN, _decision("probing", 0.99, scope_safe=0.50), cfg, scope)
    assert r.outcome is Outcome.confirm_parked


def test_deterministic_out_of_scope_blocks(cfg: Engagement, scope: Scope) -> None:
    r = evaluate("https://staging.acme-lab.example/x", _decision("probing", 0.99), cfg, scope)
    assert r.outcome is Outcome.blocked


def test_exploit_never_auto_even_at_high_confidence(cfg: Engagement, scope: Scope) -> None:
    r = evaluate(IN, _decision("exploit", 0.99, scope_safe=0.99), cfg, scope)
    assert r.outcome is Outcome.confirm_parked


def test_commit_is_terminal_auto(cfg: Engagement, scope: Scope) -> None:
    r = evaluate(IN, _decision("commit", 0.10), cfg, scope)
    assert r.outcome is Outcome.auto
    assert r.action_class is ActionClass.commit


def test_fuzzing_on_no_fuzzing_path_blocks(cfg: Engagement, scope: Scope) -> None:
    # /checkout is in scope (host match) but on the no_fuzzing_on list.
    r = evaluate("https://acme-lab.example/checkout/x", _decision("fuzzing", 0.99), cfg, scope)
    assert r.outcome is Outcome.blocked
