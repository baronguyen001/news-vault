from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from newsvault.brief import reset_provider_state

# Everything the AI Hub client reads. Cleared for every test by default.
_AI_HUB_VARS = (
    "AI_HUB_BASE_URL",
    "AI_HUB_KEY",
    "AI_HUB_MODEL",
    "AI_HUB_TIMEOUT",
    "AI_HUB_ENABLED",
)


@pytest.fixture(autouse=True)
def _no_ai_hub() -> Iterator[None]:
    """Keep the hub unreachable unless a test opts in.

    `newsvault.ai_hub` reads its settings from the environment at call time, so a developer
    who happens to have the real keys exported would silently make the brief tests reach a
    live service — slow, flaky and billable. A test that wants the hub sets the variables
    itself with `monkeypatch.setenv`, which runs later and is undone first.

    Deliberately does NOT depend on the `monkeypatch` fixture. An autouse fixture in a
    root conftest that requests `monkeypatch` forces that fixture to be created before
    every module-level autouse fixture in the whole suite — and therefore torn down after
    them. `tests/test_build_state.py` has an autouse fixture whose teardown calls
    `build._shell_digest.cache_clear()`, which then ran while the test's own
    `monkeypatch.setattr` on that same attribute was still in place, and three tests blew
    up on teardown with `'function' object has no attribute 'cache_clear'`. Saving and
    restoring the variables by hand keeps this fixture out of everyone else's ordering.
    """
    saved = {name: os.environ.pop(name, None) for name in _AI_HUB_VARS}
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@pytest.fixture(autouse=True)
def _reset_brief_provider_state() -> Iterator[None]:
    """Do not let a process-local Gemini key failure leak between tests."""
    reset_provider_state()
    try:
        yield
    finally:
        reset_provider_state()
