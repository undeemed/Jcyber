# Jcyber — agent conventions (Claude)

See **`AGENTS.md`** for the canonical conventions (this file mirrors it; keep
them in sync). Quick hits:

- This repo is the **plan** for an agent-driven BB/pentest framework:
  HexStrike (hands) + Jev/TypeSafe (reflex, sole model in control path) +
  Memgraph (session brain, per-engagement graph) + TencentDB Agent Memory
  (long-term brain, 2-method seam) + Prometheus harness (doctrine only).
- **TOON** for all machine-written config/state (`.toon` = `@toon-format/cli`
  encoder output from JSON; validate with `npx -y @toon-format/cli`).
  Canonical encodings: `schema/storage-layout.md`.
- **Thresholds are byte-identical across files** — canonical set in
  `config/decision-catalog.md` (gates `0.80/0.85/0.90/0.90/0.95/0.95`,
  `scope_model_floor 0.90`, promote ≥ 0.80, retire ≤ 0.20,
  `report_ready ≥ 0.95`). Change all occurrences together or not at all.
- **Scope gate = two layers, both must pass:** deterministic string match
  against `scope.toon` AND `scope_safe` noul ≥ 0.90. Out-of-scope wins.
- **Decision atomicity:** one `system_one` per loop iteration; atomic
  questions only; composites (e.g. `0.7·severity + 0.3·bounty`) combined in
  code — never asked as one question.
- **No free-form command construction:** HexStrike = (tool, closed-set
  params); Jev text never reaches a shell/path/URL (loop.md §4).
- **TencentDB:** recall at intake, commit at close; never in the hot loop;
  backend is swappable (`schema/tencentdb/memory-interface.md`).
- **HexStrike:** hands only — never its `bugbounty_*`/`ai_*`/
  `/api/intelligence/*` (its v6 "engine" = hard-coded heuristics, no
  BYOK). The BYOK engine is ours: Jev-dispatched (`route_via_engine`,
  atomic), Cerebras key from operator env, evidence-only — a second
  decision layer is the failure mode we avoid.
- `engagements/` gitignored (never committed); `docs/` =
  `diagrams.md` (Mermaid stack + gate diagrams) + `FAQ.md` (FAQ,
  comparison, legal note) + `RUNBOOK.md` (live bring-up).
- Runtime: `jcyber/` = reflex core + adapters (`clients/`);
  `jcyber/intake.py` = bare-link intake (scope-only synthesis — full scan
  + critical; **no gate values in code**, invariant #2); TOON through the
  codec port only (invariant #1). `tests/` = pytest; `scripts/check_docs.sh`
  + `.github/workflows/ci.yml` enforce invariants #1 and #2.
- Docs discipline: external-system claims (Memgraph/HexStrike/TencentDB/Jev)
  match current docs/source; re-fetch before correcting.