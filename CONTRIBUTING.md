# Contributing to Jcyber

Read [`AGENTS.md`](AGENTS.md) before changing anything - it holds the
invariants (scope gate is code-enforced, exploit tools require confirmation,
finding lifecycle is strict, TOON files are encoder output).

## Setup

```
uv sync
```

## Before you push

Run everything CI runs, locally - all three must be green:

```
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run pyright
```

## Commit messages: Conventional Commits

Commits follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

- **type** - one of `feat`, `fix`, `docs`, `refactor`, `perf`, `test`,
  `build`, `ci`, `chore`, `revert`.
- **scope** (optional) - the area touched, e.g. `mcp`, `scope`, `hexstrike`,
  `memgraph`, `report`, `trace`, `intake`, `docs`.
- **description** - imperative mood, lower case, no trailing period.
- **breaking change** - append `!` after the type/scope or add a
  `BREAKING CHANGE:` footer.

Examples:

```
feat(mcp): add graphql_scanner tool
fix(scope): handle IPv6 targets in scope gate
docs(readme): update quick start for MCP server
refactor(hexstrike): consolidate endpoint slug mapping
```

## Pull requests

- Keep the diff focused. When you change a contract, migrate every caller in
  the same PR.
- Do not add agent co-author trailers.
- Confirm the three gates above are green.
