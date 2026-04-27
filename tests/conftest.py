import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relpath: str):
    """Load a hyphenated-filename Python script as a module.

    Tile scripts use kebab-case filenames (e.g. `check-unanswered.py`)
    that aren't valid Python module identifiers, so they can't be
    imported normally. Each call returns a fresh module instance so
    tests that monkeypatch module-level constants (CHAT_JID, DB) don't
    leak state across tests."""
    path = REPO_ROOT / relpath
    # Most fixture misconfigurations are bad relpaths. `spec_from_file_location`
    # generally returns a non-None spec/loader even for nonexistent files —
    # the failure only shows up later inside `exec_module` as `FileNotFoundError`
    # / `OSError`. Check existence up front for the common case, keep the
    # spec/loader guard for the unusual one (custom loaders that return None),
    # and re-raise loader-time OSErrors as `ImportError` so the test report
    # names which fixture is misconfigured at a glance.
    if not path.is_file():
        raise ImportError(f"Could not load module {name!r} from {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module {name!r} from {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except OSError as exc:
        raise ImportError(f"Could not load module {name!r} from {path}") from exc
    return module


@pytest.fixture
def check_unanswered():
    """Fresh-loaded module under test. Don't cache across tests — the
    script reads NANOCLAW_CHAT_JID and NANOCLAW_DB at import time, so
    the module's CHAT_JID/DB constants are baked from the env at load.
    Tests that need to vary those should also reload, which is what
    this per-test fixture provides."""
    return _load(
        "check_unanswered_under_test",
        "skills/check-unanswered/scripts/check-unanswered.py",
    )
