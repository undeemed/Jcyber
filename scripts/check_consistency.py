#!/usr/bin/env python3
"""Jcyber doc consistency checks.

Checks:
1. TOON fenced blocks round-trip through @toon-format/cli.
2. Mermaid architecture diagram in PLAN.md matches docs/diagrams.md.
3. README Layout paths all exist on disk.
4. No TODO/FIXME/TBD/WIP markers in docs.
5. Internal Markdown links resolve (file + anchor).
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
    .gitignore, relative to ROOT."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        cwd=ROOT,
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
    inside = False
    lang = ""
    start = 0
    lines: list[str] = []
    for n, ln in enumerate(text.splitlines(), 1):
        m = FENCE.match(ln)
        if m and not inside:
            inside, lang, start, lines = True, m.group(1).lower(), n, []
        elif ln.startswith("```") and inside:
            out.append((lang, start, "\n".join(lines)))
            inside = False
        elif inside:
            lines.append(ln)
    return out


def strip_leading_comments(toon_body: str) -> str:
    """The encoder never emits `# ...` comment lines; the docs add one as a
    human label. Strip so the round-trip check passes."""
    kept = [ln for ln in toon_body.splitlines() if not ln.startswith("#")]
    return "\n".join(kept).strip("\n")


def toon(args: list[str], stdin: str) -> tuple[int, str, str]:
    p = subprocess.run(
        ["npx", "-y", "@toon-format/cli", *args],
        input=stdin,
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stdout, p.stderr


def toon_encode(obj: object) -> str | None:
    rc, out, err = toon([], json.dumps(obj))
    if rc != 0:
        fail(f"toon encode failed: {err.strip()}")
        return None
    return out.strip("\n")


def toon_decode(body: str) -> tuple[dict | list | None, str]:  # type: ignore[type-arg]
    rc, out, err = toon(["--decode"], body)
    if rc != 0:
        return None, err.strip()
    return json.loads(out), ""


# --------------------------------------------------------------------------- #
# check 1 -- TOON blocks
# --------------------------------------------------------------------------- #
def check_toon_blocks() -> None:
    md_files = sorted(p for p in repo_files() if p.suffix == ".md")
    checked = 0
    for path in md_files:
        try:
            blocks = fenced_blocks(path.read_text())
        except Exception:
            continue
        for lang, line, body in blocks:
            if lang != "toon":
                continue
            stripped = strip_leading_comments(body)
            if not stripped.strip():
                continue
            obj, err = toon_decode(stripped)
            if obj is None:
                fail(f"{path.relative_to(ROOT)}:{line} TOON decode failed: {err}")
                continue
            rt = toon_encode(obj)
            if rt is None:
                continue
            if strip_leading_comments(rt) != strip_leading_comments(stripped):
                fail(
                    f"{path.relative_to(ROOT)}:{line} TOON round-trip mismatch "
                    f"(decode+encode != original)"
                )
            checked += 1
    if checked == 0:
        fail("check_toon_blocks found zero ```toon blocks -- extractor is broken")


# --------------------------------------------------------------------------- #
# check 2 -- mermaid architecture diagram sync
# --------------------------------------------------------------------------- #
def first_mermaid(rel: str) -> str | None:
    for lang, _line, body in fenced_blocks(read(rel)):
        if lang == "mermaid":
            return body
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
# check 3 -- README manifest paths exist
# --------------------------------------------------------------------------- #
def check_manifest() -> None:
    text = read("README.md")
    m = re.search(r"^## Layout\s*$(.+?)^## ", text, re.S | re.M)
    section = m.group(1) if m else ""
    if not section:
        fail("README.md has no '## Layout' section")
        return
    # Strip fenced code blocks — paths inside them are display-only
    cleaned = strip_fences(section)
    for path in re.findall(r"`([^`]+)`", cleaned):
        if "/" not in path and not path.endswith(".md"):
            continue  # not a path reference
        if not (ROOT / path).exists():
            fail(f"README Layout points at missing path: {path}")


# --------------------------------------------------------------------------- #
# check 4 -- unfinished-work markers
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
# check 5 -- internal markdown links resolve (file + anchor)
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
