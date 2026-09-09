"""Tests for current-tz/scripts/read-current-tz.py.

Locks down the surface-helper contract per `coding-policy:
testing-standards`:

  - resolves `tz_state.current_tz` when the singleton row carries the
    supported `schema_version` and a valid IANA zone
  - degrades to `available: false` (never crashes) on every miss:
    no row, empty current_tz, unsupported schema_version, unparseable
    zone, or an unreadable DB
  - main() always emits one line of JSON and exits 0; CLI misuse exits 2
  - `home_tz` is never used as a fallback

Fixed test data per the determinism rule — no generated inputs.
"""

import json
import sqlite3


def _insert(db_path, *, current_tz, home_tz="America/New_York", schema_version):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO tz_state (id, current_tz, home_tz, schema_version) VALUES (1, ?, ?, ?)",
            (current_tz, home_tz, schema_version),
        )
        conn.commit()
    finally:
        conn.close()


def test_resolves_current_tz_on_supported_row(read_current_tz):
    module, db_path = read_current_tz
    _insert(
        db_path,
        current_tz="America/Chicago",
        schema_version=module.SUPPORTED_TZ_STATE_SCHEMA_VERSION,
    )
    assert module.resolve_current_tz() == "America/Chicago"


def test_no_row_unavailable(read_current_tz):
    module, _ = read_current_tz
    assert module.resolve_current_tz() is None


def test_unsupported_schema_version_unavailable(read_current_tz):
    """A higher/lower schema_version is 'no usable state' for a non-owner
    reader — degrade rather than guess the shape."""
    module, db_path = read_current_tz
    _insert(
        db_path,
        current_tz="America/Chicago",
        schema_version=module.SUPPORTED_TZ_STATE_SCHEMA_VERSION + 1,
    )
    assert module.resolve_current_tz() is None


def test_empty_current_tz_unavailable(read_current_tz):
    module, db_path = read_current_tz
    _insert(db_path, current_tz="   ", schema_version=module.SUPPORTED_TZ_STATE_SCHEMA_VERSION)
    assert module.resolve_current_tz() is None


def test_home_tz_is_not_a_fallback(read_current_tz):
    """A blank current_tz does NOT fall back to home_tz — relative-date
    phrasing needs where the operator is now."""
    module, db_path = read_current_tz
    _insert(
        db_path,
        current_tz="",
        home_tz="America/Los_Angeles",
        schema_version=module.SUPPORTED_TZ_STATE_SCHEMA_VERSION,
    )
    assert module.resolve_current_tz() is None


def test_invalid_zone_unavailable(read_current_tz):
    module, db_path = read_current_tz
    _insert(
        db_path,
        current_tz="Not/ARealZone",
        schema_version=module.SUPPORTED_TZ_STATE_SCHEMA_VERSION,
    )
    assert module.resolve_current_tz() is None


def test_unreadable_db_unavailable(read_current_tz, tmp_path, monkeypatch):
    """No tz_state table (fresh/other DB) degrades to unavailable, not a
    crash — the surface still fires with explicit-date phrasing."""
    module, _ = read_current_tz
    monkeypatch.setattr(module, "DB_PATH", str(tmp_path / "no-tz-table.db"))
    assert module.resolve_current_tz() is None


def test_main_emits_single_line_json_available(read_current_tz, monkeypatch, capsys):
    module, db_path = read_current_tz
    _insert(
        db_path, current_tz="Europe/Madrid", schema_version=module.SUPPORTED_TZ_STATE_SCHEMA_VERSION
    )
    monkeypatch.setattr("sys.argv", ["read-current-tz.py"])
    code = module.main()
    assert code == 0
    out = capsys.readouterr().out
    lines = [ln for ln in out.split("\n") if ln]
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"available": True, "tz": "Europe/Madrid"}


def test_main_emits_unavailable_shape(read_current_tz, monkeypatch, capsys):
    module, _ = read_current_tz  # no row inserted
    monkeypatch.setattr("sys.argv", ["read-current-tz.py"])
    code = module.main()
    assert code == 0
    assert json.loads(capsys.readouterr().out) == {"available": False, "tz": None}


def test_main_rejects_extra_args(read_current_tz, monkeypatch, capsys):
    module, _ = read_current_tz
    monkeypatch.setattr("sys.argv", ["read-current-tz.py", "/some/path"])
    assert module.main() == 2
    assert "Usage" in capsys.readouterr().err
