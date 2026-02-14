# AGENTS.md

Guidance for coding agents working in this repository.

## Scope and priorities

- This project is a Home Assistant custom integration: `custom_components/thermozona`.
- Primary language is Python.
- Prefer minimal, focused changes that align with existing patterns.
- Do not introduce new frameworks or tooling unless explicitly requested.

## Rule files check

- `.cursorrules`: not present.
- `.cursor/rules/`: not present.
- `.github/copilot-instructions.md`: not present.
- If any of these are added later, treat them as required inputs and update this file.

## Repository layout

- Integration code: `custom_components/thermozona/`.
- Tests: `tests/`.
- Example HA config: `configuration.yaml.example`.
- Docs: `README.md` and `docs/`.
- CI workflows: `.github/workflows/`.

## Environment setup

- Python 3.11+ recommended.
- Create a virtual environment:
- `python3 -m venv .venv`
- `source .venv/bin/activate`
- Upgrade pip:
- `python -m pip install -U pip`
- Install local test dependencies (repo has no pinned dev requirements file):
- `python -m pip install pytest pytest-asyncio voluptuous`

## Build, lint, and test commands

There is no compile/build pipeline for this integration, but use these checks.

- Run all tests:
- `python -m pytest -q`
- Run verbose tests:
- `python -m pytest -vv`
- Run a single test file:
- `python -m pytest tests/test_thermozona.py -q`
- Run a single test function:
- `python -m pytest tests/test_thermozona.py::test_pwm_pi_output_is_clamped -q`
- Run tests matching an expression:
- `python -m pytest -k pwm -q`
- Run only async-marked tests:
- `python -m pytest -m asyncio -q`

Optional local sanity checks when touching many files:

- Bytecode compile check:
- `python -m compileall custom_components tests`
- Import smoke check:
- `python -c "import custom_components.thermozona"`

## CI checks in this repo

- `hassfest` workflow validates Home Assistant integration metadata.
- `hacs-validate` workflow validates HACS integration structure.
- There is currently no dedicated CI workflow for running `pytest`.
- If you add test CI, keep it separate from metadata validation for fast feedback.

## Testing conventions

- Test framework is `pytest`.
- Async tests use `@pytest.mark.asyncio`.
- `tests/conftest.py` provides a lightweight fake Home Assistant environment.
- Prefer unit tests for controller and thermostat logic.
- Add regression tests with bug fixes.
- Keep tests deterministic; avoid real time waits and network access.

## Code style: imports

- Use `from __future__ import annotations` in modules that already use it.
- Group imports in this order:
- standard library
- third-party libraries
- Home Assistant imports
- local package imports
- Prefer explicit imports over wildcard imports.
- Keep one import per line when practical.

## Code style: formatting and structure

- Follow existing PEP 8 style and line lengths used in the repo.
- Use module and function docstrings (triple double quotes).
- Prefer guard clauses and early returns to reduce nesting.
- Keep methods focused; extract helpers for repeated logic.
- Avoid adding comments for obvious code.
- Preserve readability over cleverness.

## Code style: typing

- Use modern built-in generics: `list[str]`, `dict[str, Any]`.
- Use union operator `|` for optional and union types.
- Type annotate public functions and important internal helpers.
- Keep `Any` usage minimal and intentional.
- For HA entities, keep attribute types explicit when useful.

## Naming conventions

- Constants: uppercase with underscores (for config keys/defaults).
- Classes: PascalCase.
- Functions and variables: snake_case.
- Internal attributes/methods: leading underscore.
- Entity IDs/unique IDs should be stable and deterministic.

## Home Assistant integration patterns

- Respect entity lifecycle hooks:
- `async_added_to_hass`
- `async_will_remove_from_hass`
- Use `async_write_ha_state()` after state updates.
- Register and unregister controller callbacks symmetrically.
- Keep platform setup in `async_setup_entry` functions.
- Reuse shared controller instances via `hass.data[DOMAIN]["controllers"]`.

## Error handling and logging

- Prefer graceful degradation for bad entity state or missing sensors.
- Parse external state defensively (catch `TypeError`/`ValueError`).
- Log expected runtime issues with `_LOGGER.warning`.
- Log exceptional conversion/logic failures with `_LOGGER.error`.
- Raise explicit exceptions only for invalid API usage that should fail fast.
- Never swallow exceptions silently.

## Config and schema changes

- Keep config keys centralized in `custom_components/thermozona/__init__.py`.
- Update `CONFIG_SCHEMA` and defaults together.
- Preserve backward compatibility where possible (example: legacy key fallback).
- Reflect new options in docs and example YAML.

## When modifying behavior

- Update both runtime logic and tests in the same change.
- Add tests near related scenarios in `tests/test_thermozona.py`.
- Validate both heating and cooling paths when touching control logic.
- Consider idle/off transitions and restoration behavior.

## Files agents should check before major edits

- `custom_components/thermozona/__init__.py`
- `custom_components/thermozona/heat_pump.py`
- `custom_components/thermozona/thermostat.py`
- `tests/test_thermozona.py`
- `tests/conftest.py`
- `README.md`

## Branch workflow

- Default to working on a feature branch, not `main`.
- Use descriptive branch names such as `codex/<short-kebab-topic>` or `feature/<short-kebab-topic>`.
- Push first time with upstream tracking: `git push -u origin <branch>`.
- Before opening a PR, ensure the branch is clean and has an upstream.

## Commit and PR guidance

- Keep commits scoped to one logical change.
- Include tests for logic changes.
- In PR descriptions, explain why behavior changed and how it was validated.
- Mention follow-ups explicitly if scope was intentionally limited.

## Git and GitHub workflow notes

- Before committing, check `git diff --stat` to catch accidental artifacts or deletes.
- Avoid committing runtime files/log artifacts unless explicitly requested.
- Create PRs with GitHub CLI (`gh pr create`) and include both summary and testing notes.
- If Git reports a repository move, treat `thermozona/thermozona` as the canonical GitHub location.

## Agent behavior expectations

- Prefer repository conventions over personal defaults.
- Do not rewrite unrelated files.
- Do not remove backward-compatibility paths without explicit instruction.
- If a command/tool is missing, state assumptions and proceed conservatively.
