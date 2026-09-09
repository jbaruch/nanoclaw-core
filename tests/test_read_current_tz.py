"""Tests for current-tz/scripts/read-current-tz.py.

Locks down the shared-reader contract per `coding-policy:
testing-standards`:

  - resolves `tz_state.current_tz` when the singleton row carries the
    supported `schema_version` and a valid IANA zone, and expresses a
    pinned instant in it (`local_now`, `local_date`)
  - degrades to `available: false` at exit 0 on every expected miss:
    no row, empty current_tz, unsupported schema_version, unparseable
    zone
  - exits 1 (still emitting the unavailable shape) when the store
    itself cannot be read
  - CLI misuse (unknown argument, naive --now) exits 2
  - `home_tz` is never used as a fallback

Fixed test data per the determinism rule — every instant is pinned
through `--now`; no test reads the clock.
"""

import json
import sqlite3

import pytest

PINNED_NOW = "2026-09-10T05:31:00Z"


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


def _run(module, capsys, *argv):
    code = module.main(list(argv))
    out = capsys.readouterr()
    lines = [ln for ln in out.out.split("\n") if ln]
    assert len(lines) == 1, out.out
    return code, json.loads(lines[0]), out.err


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
    """A blank current_tz does NOT fall back to home_tz — the answer is
    where the operator is now."""
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


def test_unreadable_store_raises(read_current_tz, tmp_path, monkeypatch):
    """A store with no tz_state table is an operational failure, not an
    'unavailable' answer — the function raises so main() can exit 1."""
    module, _ = read_current_tz
    monkeypatch.setattr(module, "DB_PATH", str(tmp_path / "no-tz-table.db"))
    with pytest.raises(module.StoreUnreadable):
        module.resolve_current_tz()


def test_main_available_carries_local_now_and_date(read_current_tz, capsys):
    module, db_path = read_current_tz
    _insert(
        db_path, current_tz="Europe/Madrid", schema_version=module.SUPPORTED_TZ_STATE_SCHEMA_VERSION
    )
    code, payload, _ = _run(module, capsys, "--now", PINNED_NOW)
    assert code == 0
    # 05:31Z on Sept 10 is 07:31 CEST the same day.
    assert payload == {
        "available": True,
        "tz": "Europe/Madrid",
        "local_now": "2026-09-10T07:31:00+02:00",
        "local_date": "2026-09-10",
    }


def test_main_local_date_crosses_midnight(read_current_tz, capsys):
    """05:31Z is still Sept 9 in Chicago — the local date is the zone's,
    not UTC's."""
    module, db_path = read_current_tz
    _insert(
        db_path,
        current_tz="America/Chicago",
        schema_version=module.SUPPORTED_TZ_STATE_SCHEMA_VERSION,
    )
    code, payload, _ = _run(module, capsys, "--now", PINNED_NOW)
    assert code == 0
    assert payload["local_now"] == "2026-09-10T00:31:00-05:00"
    assert payload["local_date"] == "2026-09-10"
    code, payload, _ = _run(module, capsys, "--now", "2026-09-10T04:31:00Z")
    assert payload["local_date"] == "2026-09-09"


def test_main_emits_unavailable_shape_at_exit_0(read_current_tz, capsys):
    module, _ = read_current_tz  # no row inserted
    code, payload, err = _run(module, capsys, "--now", PINNED_NOW)
    assert code == 0
    assert payload == {"available": False, "tz": None, "local_now": None, "local_date": None}
    assert "no singleton row" in err


def test_main_exits_1_when_store_unreadable(read_current_tz, tmp_path, monkeypatch, capsys):
    """Missing file / no table: still the unavailable shape on stdout so a
    surface can degrade, but exit 1 so a scheduling caller sees the
    operational failure."""
    module, _ = read_current_tz
    monkeypatch.setattr(module, "DB_PATH", str(tmp_path / "missing.db"))
    code, payload, err = _run(module, capsys, "--now", PINNED_NOW)
    assert code == 1
    assert payload["available"] is False
    assert "cannot read tz_state" in err


def test_main_rejects_naive_now(read_current_tz, capsys):
    module, _ = read_current_tz
    assert module.main(["--now", "2026-09-10T05:31:00"]) == 2
    assert "offset" in capsys.readouterr().err


def test_main_rejects_unknown_args(read_current_tz, capsys):
    module, _ = read_current_tz
    assert module.main(["/some/path"]) == 2
    assert "usage" in capsys.readouterr().err.lower()
