"""Typed engagement + scope config, parsed from the TOON files. Every
threshold the loop uses is loaded from here (engagement.toon) -- the code
holds no hard-coded gate values."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .ports import ToonCodec
from .types import JSON, Scope, ScopeItem, Severity


# --- narrowing helpers: decoded TOON is loose JSON, coerce with validation ---
def _obj(v: JSON) -> dict[str, JSON]:
    if not isinstance(v, dict):
        raise ValueError(f"expected object, got {type(v).__name__}")
    return v


def _arr(v: JSON) -> list[JSON]:
    if not isinstance(v, list):
        raise ValueError(f"expected array, got {type(v).__name__}")
    return v


def _str(v: JSON) -> str:
    if not isinstance(v, str):
        raise ValueError(f"expected string, got {type(v).__name__}")
    return v


def _num(v: JSON) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise ValueError(f"expected number, got {type(v).__name__}")
    return float(v)


def _int(v: JSON) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(f"expected int, got {type(v).__name__}")
    return v


def _bool(v: JSON) -> bool:
    if not isinstance(v, bool):
        raise ValueError(f"expected bool, got {type(v).__name__}")
    return v


def _opt_str(v: JSON | None) -> str | None:
    return None if v is None else _str(v)


@dataclass(frozen=True)
class Gate:
    auto: float
    fallback: str  # the TOON key is `else`, a Python keyword


@dataclass(frozen=True)
class Verdicts:
    promote: float
    retire: float


@dataclass(frozen=True)
class EngineCfg:
    enabled: bool
    provider: str
    model: str
    model_trivial: str


@dataclass(frozen=True)
class Engagement:
    target: str
    program: str
    jev_model: str
    state_budget_chars: int
    gates: dict[str, Gate]
    verdicts: Verdicts
    report_ready: float
    budget: dict[str, int]
    caido_proxy: str
    engine: EngineCfg

    @classmethod
    def from_json(cls, data: JSON) -> Engagement:
        d = _obj(data)
        jev = _obj(d["jev"])
        gates = {
            k: Gate(auto=_num(_obj(v)["auto"]), fallback=_str(_obj(v)["else"]))
            for k, v in _obj(d["gates"]).items()
        }
        verdicts = _obj(d["verdicts"])
        engine = _obj(d["engine"])
        return cls(
            target=_str(d["target"]),
            program=_str(d["program"]),
            jev_model=_str(jev["model"]),
            state_budget_chars=_int(jev["state_budget_chars"]),
            gates=gates,
            verdicts=Verdicts(promote=_num(verdicts["promote"]), retire=_num(verdicts["retire"])),
            report_ready=_num(d["report_ready"]),
            budget={k: _int(v) for k, v in _obj(d["budget"]).items()},
            caido_proxy=_str(_obj(d["caido"])["proxy"]),
            engine=EngineCfg(
                enabled=_bool(engine["enabled"]),
                provider=_str(engine["provider"]),
                model=_str(engine["model"]),
                model_trivial=_str(engine["model_trivial"]),
            ),
        )


def _scope_item(v: JSON) -> ScopeItem:
    d = _obj(v)
    return ScopeItem(kind=_str(d["kind"]), value=_str(d["value"]), note=_opt_str(d.get("note")))


def _severity(v: JSON) -> Severity:
    s = _str(v)
    try:
        return Severity(s)
    except ValueError as e:
        raise ValueError(
            f"illegal severity_focus: {s!r} (want none|low|medium|high|critical)"
        ) from e


def scope_from_json(data: JSON) -> Scope:
    d = _obj(data)
    c = _obj(d["constraints"])
    return Scope(
        engagement=_str(d["engagement"]),
        in_scope=[_scope_item(i) for i in _arr(d["in_scope"])],
        out_of_scope=[_scope_item(i) for i in _arr(d["out_of_scope"])],
        no_fuzzing_on=[_str(x) for x in _arr(c["no_fuzzing_on"])],
        authorized_accounts=[_str(x) for x in _arr(c["authorized_accounts"])],
        rate_limit_rps=_int(c["rate_limit_rps"]),
        time_window=_str(c["time_window"]),
        severity_focus=_severity(c.get("severity", "critical")),
    )


def load_engagement(path: Path, codec: ToonCodec) -> Engagement:
    return Engagement.from_json(codec.decode(path.read_text()))


def load_scope(path: Path, codec: ToonCodec) -> Scope:
    return scope_from_json(codec.decode(path.read_text()))
