import importlib.util
import sqlite3 as _sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relpath: str):
    """Load a hyphenated-filename Python script as a module.

    Plugin scripts use kebab-case filenames (e.g. `query-message-history.py`)
    that aren't valid Python module identifiers, so they can't be
    imported normally. Each call returns a fresh module instance so
    tests that monkeypatch module-level constants don't leak state
    across tests."""
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
def query_message_history():
    """Fresh-loaded module under test for the query-history skill's
    messages.db keyword/sender query helper. Per-test reload so tests
    that monkeypatch env or module-level constants don't leak state
    across tests."""
    return _load(
        "query_message_history_under_test",
        "skills/query-history/scripts/query-message-history.py",
    )


@pytest.fixture
def now_vs_deadline():
    """Fresh-loaded module under test for the now-vs-deadline skill's
    deadline-comparison helper. The module exposes `compare(now,
    deadline)` and `parse_deadline(str)` as pure functions so tests can
    pin `now` and assert deterministic past/future output. Per-test
    reload matches the pattern above."""
    return _load(
        "now_vs_deadline_under_test",
        "skills/now-vs-deadline/scripts/now-vs-deadline.py",
    )


def _seed_tz_state_db(db_path: str) -> None:
    """Apply the host `tz_state` singleton DDL to a fresh SQLite file,
    mirroring the orchestrator's state-010/012 migration shape so the
    reader test stays tied to the real schema. The singleton row is NOT
    inserted — callers INSERT per scenario (or leave it empty to exercise
    the no-row branch)."""
    conn = _sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE tz_state (
              id             INTEGER PRIMARY KEY CHECK(id = 1),
              current_tz     TEXT NOT NULL,
              home_tz        TEXT NOT NULL,
              scheduler_tz   TEXT,
              schema_version INTEGER NOT NULL DEFAULT 1,
              segments       TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def read_current_tz(tmp_path, monkeypatch):
    """Load current-tz/scripts/read-current-tz.py with DB_PATH redirected
    at a tmp_path-rooted SQLite file seeded with the `tz_state` schema.
    Returned tuple is (module, db_path) — the singleton row is NOT
    inserted so callers choose row-present vs no-row.
    SUPPORTED_TZ_STATE_SCHEMA_VERSION on the loaded module is the
    version a present row must carry to be honoured."""
    db_path = tmp_path / "messages.db"
    _seed_tz_state_db(str(db_path))
    module = _load(
        "read_current_tz_under_test",
        "skills/current-tz/scripts/read-current-tz.py",
    )
    monkeypatch.setattr(module, "DB_PATH", str(db_path))
    return module, db_path
