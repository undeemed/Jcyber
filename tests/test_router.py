"""Router: class -> tool + closed-set params. Pins the no-free-form-command
discipline (params come only from cfg/scope)."""

from __future__ import annotations

from jcyber.config import Engagement
from jcyber.router import route
from jcyber.types import ActionClass, Scope

T = "https://acme-lab.example/api"


def test_probing_routes_to_preferred_tool(cfg: Engagement, scope: Scope) -> None:
    call = route(ActionClass.probing, T, cfg, scope)
    assert call is not None
    assert call.tool == "nuclei_scan"


def test_recon_passive_routes_to_preferred_tool(cfg: Engagement, scope: Scope) -> None:
    call = route(ActionClass.recon_passive, T, cfg, scope)
    assert call is not None
    assert call.tool == "subfinder_scan"
    assert "proxy" not in call.params  # passive recon runs unproxied (PLAN section 3)


def test_params_are_closed_set_only(cfg: Engagement, scope: Scope) -> None:
    call = route(ActionClass.probing, T, cfg, scope)
    assert call is not None
    assert set(call.params) <= {"target", "proxy", "no_fuzzing_on"}
    assert call.params["proxy"] == cfg.caido_proxy
    assert call.params["target"] == T


def test_fuzzing_carries_no_fuzzing_list(cfg: Engagement, scope: Scope) -> None:
    call = route(ActionClass.fuzzing, T, cfg, scope)
    assert call is not None
    assert call.tool == "ffuf_scan"
    assert call.params["no_fuzzing_on"] == scope.no_fuzzing_on


def test_report_and_commit_have_no_tool(cfg: Engagement, scope: Scope) -> None:
    assert route(ActionClass.report, T, cfg, scope) is None
    assert route(ActionClass.commit, T, cfg, scope) is None
