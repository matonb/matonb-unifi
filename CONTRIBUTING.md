# Contributing

Thanks for your interest in improving `matonb-unifi`! This project uses
[uv](https://docs.astral.sh/uv/) for environment and dependency management.

## Getting started

```bash
git clone https://github.com/matonb/matonb-unifi.git
cd matonb-unifi
uv sync --extra dev --extra test --extra typecheck
```

## Checks

All of these run in CI and must pass before a change is merged:

```bash
# Tests (with coverage; the suite must stay at or above the configured floor)
uv run --extra test pytest

# Lint and formatting
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .

# Strict static type checking
uv run --extra typecheck mypy
```

`ruff format .` (without `--check`) applies formatting, and
`ruff check --fix .` applies the auto-fixable lint fixes.

## Coding standards

- Target **Python 3.10+** — avoid APIs newer than 3.10 unless guarded
  (e.g. `typing.Self` is imported from `typing_extensions` on 3.10).
- The package is **fully typed** and ships `py.typed`; new public code needs
  type annotations and must pass `mypy --strict`.
- Public functions surface the library's own exceptions
  (`UnifiError` and subclasses), never raw `httpx` errors.
- Add or update tests for any behaviour change; network calls are mocked with
  [`respx`](https://lundberg.github.io/respx/) — tests never hit a real
  controller.

## Commit messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/);
[python-semantic-release](https://python-semantic-release.readthedocs.io/)
derives the next version, tag, changelog, and GitHub release from them on every
push to `main`.

| Prefix      | Effect on version            |
|-------------|------------------------------|
| `fix:`      | patch release (e.g. 0.1.1)   |
| `feat:`     | minor release (e.g. 0.2.0)   |
| `feat!:` / `BREAKING CHANGE:` footer | breaking release |
| `docs:`, `chore:`, `test:`, `ci:`, `refactor:` | no release |

Examples:

```
fix: carry the auth token on legacy logout requests

feat: add cycle_port_poe() power-cycle helper
```

## Reporting issues

Please open issues at
<https://github.com/matonb/matonb-unifi/issues> and include the UniFi
controller type (UDM / UniFi OS vs. legacy standalone), the library version,
and a minimal snippet that reproduces the problem.
