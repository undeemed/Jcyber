"""Normalizer: deterministic sha256 dedup key + one-line summary."""

from __future__ import annotations

from jcyber.normalize import normalize, sha256_hex


def test_sha_deterministic() -> None:
    assert sha256_hex("abc") == sha256_hex("abc")
    assert sha256_hex("abc") != sha256_hex("abd")


def test_normalize_summary_and_path() -> None:
    ev = normalize(
        "acme-lab", "nmap_scan", "acme-lab.example", "PORT 80 open\nPORT 443 open", "E-001"
    )
    assert ev.summary == "PORT 80 open | PORT 443 open"
    assert ev.sha256 == sha256_hex("PORT 80 open\nPORT 443 open")
    assert ev.raw_path == "evidence/raw/E-001.txt"
    assert ev.id == "E-001"


def test_normalize_empty_output() -> None:
    ev = normalize("acme-lab", "t", "x", "   ", "E-002")
    assert ev.summary == "(empty output)"
