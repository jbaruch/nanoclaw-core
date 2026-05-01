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


@pytest.fixture
def container_uptime():
    """Fresh-loaded module under test for the status skill's
    container-uptime script. Per-test reload keeps tests independent
    even though this module reads no module-level env."""
    return _load(
        "container_uptime_under_test",
        "skills/status/scripts/container-uptime.py",
    )


@pytest.fixture
def unanswered_precheck(tmp_path, monkeypatch):
    """Load check-unanswered/scripts/unanswered-precheck.py with the
    four module-level paths redirected at tmp_path. Returned tuple is
    (module, seen_dir, seen_file, legacy_seen_file, check_script).

    `CHECK_SCRIPT` is monkeypatched at a tmp_path location so tests
    can write fake check-unanswered.py implementations that drive
    every output branch (success, non-zero, invalid JSON, env-warning,
    bad-shape) without invoking the real check-unanswered.

    The seen_dir is NOT pre-created so callers can exercise both the
    "first run" and "post-migration" branches; the canonical seen
    file is also absent until the test explicitly writes it."""
    seen_dir = tmp_path / "check-unanswered"
    seen_file = seen_dir / "unanswered-seen.json"
    legacy_seen_file = tmp_path / "legacy" / "unanswered-seen.json"
    check_script = tmp_path / "check-unanswered.py"

    module = _load(
        "unanswered_precheck_under_test",
        "skills/check-unanswered/scripts/unanswered-precheck.py",
    )
    monkeypatch.setattr(module, "SEEN_STATE_DIR", str(seen_dir))
    monkeypatch.setattr(module, "SEEN_FILE", str(seen_file))
    monkeypatch.setattr(module, "LEGACY_SEEN_FILE", str(legacy_seen_file))
    monkeypatch.setattr(module, "CHECK_SCRIPT", str(check_script))
    return module, seen_dir, seen_file, legacy_seen_file, check_script
