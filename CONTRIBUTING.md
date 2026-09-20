# Contributing to Jcyber

Jcyber is docs-first: the specs in `PLAN.md`, `schema/`, `config/`, and
`orchestrator/` are load-bearing, and the code implements them. Read
[`AGENTS.md`](AGENTS.md) before changing anything - it holds the invariants
(TOON files are `@toon-format/cli` output, gate thresholds live in one place
and stay byte-identical, the scope gate is two mandatory layers, and no gate
value appears in Python).

## Setup

```
uv sync
```

## Before you push

Run everything CI runs, locally - all four must be green:

```
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run pyright
bash scripts/check_docs.sh
```

CI (`.github/workflows/ci.yml`) runs the same plus a Dockerized Memgraph smoke.

## Commit messages: Conventional Commits

Commits follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

- **type** - one of `feat`, `fix`, `docs`, `refactor`, `perf`, `test`,
  `build`, `ci`, `chore`, `revert`.
- **scope** (optional) - the area touched, e.g. `loop`, `gate`, `scope`,
  `hexstrike`, `caido`, `memgraph`, `tencentdb`, `report`, `trace`, `intake`,
  `docs`.
- **description** - imperative mood, lower case, no trailing period.
- **breaking change** - append `!` after the type/scope (`feat(gate)!: ...`)
  or add a `BREAKING CHANGE:` footer (or both).

`feat` maps to a minor release, `fix` to a patch, a `BREAKING CHANGE` to a
major. Examples:

```
feat(trace): render the :Decision audit for an engagement
fix(report): order evidence by id so the Markdown is deterministic
docs(readme): add a service-usage diagram and a filetree layout
refactor(hexstrike): map MCP tool names to REST slugs in one table
```

## Pull requests

- Keep the diff focused. When you change a contract, migrate every caller in
  the same PR; do not leave shims or dead aliases.
- Do not add agent co-author trailers. The human who opens the PR is
  accountable for it; record model/session as metadata if you want, not as an
  author.
- Confirm the four gates above are green and that no gate value
  (`0.80` / `0.85` / `0.90` / `0.95`) leaked into Python.
