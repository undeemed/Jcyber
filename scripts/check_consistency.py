#!/usr/bin/env python3
"""Jcyber spec-doc consistency checks (P0 self-check).

No threshold value is hard-coded here. Values are parsed FROM the docs
(the engagement.toon JSON block and config/decision-catalog.md are the
designated homes, per AGENTS.md invariant #2) and every other file is
asserted to agree by parsed numeric value -- not raw bytes, because the
TOON encoder normalizes 0.80 -> 0.8.

Checks:
  1. Every fenced ```toon block round-trips through @toon-format/cli, and
     each block that is paired with an adjacent ```json block is exactly
     the encoder output of that JSON (invariant #1).
  2. Gate thresholds are value-identical across the canonical files
     (invariant #2).
  3. PLAN.md and docs/diagrams.md carry the same architecture mermaid.
  4. README 'Layout' manifest points only at paths that exist.
  5. No unfinished-work markers (TODO/FIXME/TBD/...) in tracked docs.

Exit 0 iff all invariants hold.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES: list[str] = []


def repo_files() -> list[Path]:
    """Working-tree files git would track: cached + untracked, honoring
    .gitignore (so .venv, __pycache__, engagements/, build/ never appear)."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [ROOT / line for line in out.stdout.splitlines() if line]


def fail(msg: str) -> None:
    FAILURES.append(msg)


def read(rel: str) -> str:
    return (ROOT / rel).read_text()


# --------------------------------------------------------------------------- #
# fenced-block + TOON helpers
# --------------------------------------------------------------------------- #
FENCE = re.compile(r"^```([A-Za-z0-9_-]*)\s*$")


def fenced_blocks(text: str) -> list[tuple[str, int, str]]:
    """Return (lang, start_line_1based, body) for every ``` fenced block."""
    out: list[tuple[str, int, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if m:
            lang = m.group(1)
            body: list[str] = []
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                body.append(lines[j])
                j += 1
            out.append((lang, i + 1, "\n".join(body)))
            i = j + 1
        else:
            i += 1
    return out


def strip_leading_comments(toon_body: str) -> str:
    """The encoder never emits `# ...` comment lines; the docs add one as a
    caption. Drop leading comment lines before comparing to encoder output."""
    kept = [ln for ln in toon_body.splitlines() if not ln.lstrip().startswith("#")]
    return "\n".join(kept).strip("\n")


def toon(args: list[str], stdin: str) -> tuple[int, str, str]:
    p = subprocess.run(
        ["npx", "-y", "@toon-format/cli", *args],
        input=stdin,
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stdout, p.stderr


def toon_encode(obj) -> str | None:
    rc, out, err = toon([], json.dumps(obj))
    if rc != 0:
        fail(f"toon encode failed: {err.strip()}")
        return None
    return out.strip("\n")


def toon_decode(body: str) -> tuple[dict | list | None, str]:
    rc, out, err = toon(["--decode"], body)
    if rc != 0:
        return None, err.strip()
    return json.loads(out), ""


# --------------------------------------------------------------------------- #
# check 1 -- TOON blocks
# --------------------------------------------------------------------------- #
def check_toon_blocks() -> None:
    md_files = sorted(p for p in repo_files() if p.suffix == ".md")
    toon_count = 0
    for path in md_files:
        rel = path.relative_to(ROOT)
        blocks = fenced_blocks(path.read_text())
        for idx, (lang, line, body) in enumerate(blocks):
            if lang != "toon":
                continue
            toon_count += 1
            clean = strip_leading_comments(body)
            decoded, err = toon_decode(clean)
            if decoded is None:
                fail(f"{rel}:{line} ```toon does not decode (strict): {err}")
                continue
            # pair with an adjacent ```json block that starts right after
            pair = None
            for nlang, _nline, nbody in blocks[idx + 1 : idx + 3]:
                if nlang == "json":
                    pair = nbody
                    break
            if pair is None:
                continue
            try:
                pj = json.loads(pair)
            except json.JSONDecodeError as e:
                fail(f"{rel}:{line} paired ```json is not valid JSON: {e}")
                continue
            if decoded != pj:
                fail(f"{rel}:{line} ```toon does not round-trip to its paired JSON")
            enc = toon_encode(pj)
            if enc is not None and enc != clean:
                fail(f"{rel}:{line} ```toon is not exact encoder output of its JSON (invariant #1)")
    if toon_count == 0:
        fail("check_toon_blocks found zero ```toon blocks -- extractor is broken")


# --------------------------------------------------------------------------- #
# check 2 -- threshold value-identity
# --------------------------------------------------------------------------- #
GATE_KEYS = ["recon_passive", "recon_active", "probing", "verify", "fuzzing", "report"]


def floats_near(text: str, keyword: str) -> set[float]:
    out: set[float] = set()
    for ln in text.splitlines():
        if keyword in ln:
            for tok in re.findall(r"\d\.\d+", ln):
                out.add(float(tok))
    return out


def parse_engagement_json() -> dict | None:
    """The engagement.toon JSON block in storage-layout.md is the machine-
    readable mirror of the catalog's canonical values."""
    for lang, _line, body in fenced_blocks(read("schema/storage-layout.md")):
        if lang == "json" and '"gates"' in body and '"verdicts"' in body:
            return json.loads(body)
    fail("could not find engagement.toon JSON block in storage-layout.md")
    return None


def parse_catalog_gate_table() -> dict[str, float]:
    """Rows like: | recon_passive | 0.80 | queue |"""
    out: dict[str, float] = {}
    for ln in read("config/decision-catalog.md").splitlines():
        m = re.match(r"^\|\s*([a-z_]+)\s*\|\s*(\d\.\d+)\s*\|", ln)
        if m and m.group(1) in GATE_KEYS:
            out[m.group(1)] = float(m.group(2))
    return out


def parse_loop_thr() -> dict[str, float]:
    """The `thr = { ... }` dict literal in orchestrator/loop.md."""
    text = read("orchestrator/loop.md")
    m = re.search(r"thr\s*=\s*\{(.+?)\}", text, re.S)
    if not m:
        fail("could not find `thr = {...}` dict in loop.md")
        return {}
    out: dict[str, float] = {}
    for k, v in re.findall(r'"([a-z_]+)":\s*(\d\.\d+)', m.group(1)):
        out[k] = float(v)
    return out


def check_thresholds() -> None:
    eng = parse_engagement_json()
    if eng is None:
        return
    ref_gates = {k: float(v["auto"]) for k, v in eng["gates"].items()}  # incl scope_model_floor
    ref_verdicts = {k: float(v) for k, v in eng["verdicts"].items()}

    # anchor sanity: engagement.toon must define every gate key we track
    for k in GATE_KEYS + ["scope_model_floor"]:
        if k not in ref_gates:
            fail(f"engagement.toon JSON missing gate '{k}'")

    # catalog action-class table must equal the machine anchor
    cat_gates = parse_catalog_gate_table()
    for k in GATE_KEYS:
        if k not in cat_gates:
            fail(f"decision-catalog.md action-class table missing row '{k}'")
        elif cat_gates[k] != ref_gates.get(k):
            fail(f"threshold '{k}': catalog {cat_gates[k]} != engagement.toon {ref_gates.get(k)}")

    # loop.md thr dict must equal the machine anchor for the six action classes
    loop_thr = parse_loop_thr()
    for k in GATE_KEYS:
        if loop_thr.get(k) != ref_gates.get(k):
            fail(
                f"threshold '{k}': loop.md thr {loop_thr.get(k)} != engagement.toon "
                f"{ref_gates.get(k)}"
            )

    # scope_model_floor present with the anchor value everywhere it is named
    smf = ref_gates.get("scope_model_floor")
    for rel in [
        "config/decision-catalog.md",
        "orchestrator/loop.md",
        "examples/idor-walkthrough.md",
        "docs/diagrams.md",
    ]:
        near = floats_near(read(rel), "scope_model_floor") | floats_near(read(rel), "scope_safe")
        if smf not in near:
            fail(f"scope_model_floor {smf} not found near scope_safe/scope_model_floor in {rel}")

    # verdicts: catalog prose must carry the anchor values
    cat = read("config/decision-catalog.md")
    if ref_verdicts["promote"] not in floats_near(cat, "promote"):
        fail(f"promote {ref_verdicts['promote']} not found near 'promote' in catalog")
    if ref_verdicts["retire"] not in floats_near(cat, "retire"):
        fail(f"retire {ref_verdicts['retire']} not found near 'retire' in catalog")

    # report_ready: catalog is its home; loop.md and idor must match that value
    rr_home = floats_near(cat, "report_ready")
    rr_candidates = {v for v in rr_home if v >= 0.9}  # 0.6 also appears on that line
    if len(rr_candidates) != 1:
        fail(f"report_ready value ambiguous/absent in catalog: {sorted(rr_home)}")
    else:
        rr = rr_candidates.pop()
        if eng.get("report_ready") != rr:
            fail(f"report_ready: engagement.toon {eng.get('report_ready')} != catalog {rr}")
        for rel in ["orchestrator/loop.md", "examples/idor-walkthrough.md"]:
            if rr not in floats_near(read(rel), "report_ready"):
                fail(f"report_ready {rr} not found near 'report_ready' in {rel}")


# --------------------------------------------------------------------------- #
# check 3 -- mermaid architecture diagram sync
# --------------------------------------------------------------------------- #
def first_mermaid(rel: str) -> str | None:
    for lang, _line, body in fenced_blocks(read(rel)):
        if lang == "mermaid":
            return "\n".join(ln.rstrip() for ln in body.splitlines()).strip("\n")
    return None


def check_mermaid() -> None:
    plan = first_mermaid("PLAN.md")
    diag = first_mermaid("docs/diagrams.md")
    if plan is None:
        fail("PLAN.md has no ```mermaid block")
    if diag is None:
        fail("docs/diagrams.md has no ```mermaid block")
    if plan and diag and plan != diag:
        pl, dl = plan.splitlines(), diag.splitlines()
        for i in range(max(len(pl), len(dl))):
            a = pl[i] if i < len(pl) else "<eof>"
            b = dl[i] if i < len(dl) else "<eof>"
            if a != b:
                fail(
                    f"architecture mermaid drift PLAN.md vs docs/diagrams.md at line {i + 1}:\n"
                    f"    PLAN: {a}\n    DIAG: {b}"
                )
                break


# --------------------------------------------------------------------------- #
# check 4 -- README manifest paths exist
# --------------------------------------------------------------------------- #
def check_manifest() -> None:
    text = read("README.md")
    m = re.search(r"^## Layout\s*$(.+?)^## ", text, re.S | re.M)
    section = m.group(1) if m else ""
    if not section:
        fail("README.md has no '## Layout' section")
        return
    for path in re.findall(r"`([^`]+)`", section):
        if "/" not in path and not path.endswith(".md"):
            continue  # not a path reference
        if not (ROOT / path).exists():
            fail(f"README Layout points at missing path: {path}")


# --------------------------------------------------------------------------- #
# check 5 -- unfinished-work markers
# --------------------------------------------------------------------------- #
MARKER = re.compile(
    r"\b(TODO|FIXME|TBD|XXX|HACK|WIP)\b|coming soon|to be written|to be determined", re.I
)


def check_placeholders() -> None:
    exts = {".md", ".cypher", ".yml", ".yaml"}
    for path in sorted(repo_files()):
        if path.suffix not in exts:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        for n, ln in enumerate(path.read_text().splitlines(), 1):
            if MARKER.search(ln):
                fail(f"{path.relative_to(ROOT)}:{n} unfinished-work marker: {ln.strip()[:80]}")


# --------------------------------------------------------------------------- #
# check 6 -- internal markdown links resolve (file + anchor)
# --------------------------------------------------------------------------- #
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)]+)\)")


def strip_fences(text: str) -> str:
    return re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)


def slugify(heading: str) -> str:
    s = heading.strip().lower().replace("`", "")
    s = re.sub(r"[^\w\s-]", "", s)
    return s.replace(" ", "-")


def headings(text: str) -> set[str]:
    return {
        slugify(m.group(1))
        for ln in strip_fences(text).splitlines()
        if (m := re.match(r"^#{1,6}\s+(.*?)\s*$", ln))
    }


def check_links() -> None:
    for path in sorted(repo_files()):
        if path.suffix != ".md":
            continue
        text = path.read_text()
        own = headings(text)
        for target in LINK.findall(strip_fences(text)):
            target = target.strip()
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            file_part, _, anchor = target.partition("#")
            if file_part == "":
                if anchor and slugify(anchor) not in own:
                    fail(f"{path.relative_to(ROOT)} broken same-file anchor: #{anchor}")
                continue
            dest = (path.parent / file_part).resolve()
            if not dest.exists():
                fail(f"{path.relative_to(ROOT)} broken link: {target}")
            elif (
                anchor
                and dest.suffix == ".md"
                and slugify(anchor) not in headings(dest.read_text())
            ):
                fail(f"{path.relative_to(ROOT)} broken anchor: {target}")


# --------------------------------------------------------------------------- #
def main() -> int:
    check_toon_blocks()
    check_thresholds()
    check_mermaid()
    check_manifest()
    check_placeholders()
    check_links()
    if FAILURES:
        print(f"check_consistency: {len(FAILURES)} failure(s)\n", file=sys.stderr)
        for f in FAILURES:
            print(f"  FAIL  {f}", file=sys.stderr)
        return 1
    print("check_consistency: all invariants hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
