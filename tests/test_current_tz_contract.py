"""Verify the authored provider closure and actual read-only output contract."""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = "/home/node/.claude/skills/tessl__current-tz/scripts/read-current-tz.py"


def test_named_provider_contract_and_native_skill_lookup_are_co_shipped():
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    assert manifest["name"] == "jbaruch/nanoclaw-core"
    assert "skills/current-tz" in manifest["skills"]
    assert "rules/temporal-awareness.md" in manifest["rules"]
    paths = [
        ROOT / "rules/temporal-awareness.md",
        ROOT / "skills/current-tz/SKILL.md",
        ROOT / "skills/current-tz/scripts/read-current-tz.py",
    ]
    for path in paths:
        assert path.is_file() and not path.is_symlink()
        assert path.resolve().is_relative_to(ROOT)
    assert NATIVE in paths[0].read_text() and NATIVE in paths[1].read_text()


def test_declared_reader_emits_real_json_without_changing_the_fixture_store(
    read_current_tz, capsys
):
    owner, database = read_current_tz
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO tz_state(id,current_tz,home_tz,schema_version) VALUES(1,?,?,?)",
            ("America/New_York", "Europe/London", owner.SUPPORTED_TZ_STATE_SCHEMA_VERSION),
        )
    before = database.read_bytes()
    assert owner.main(["--now", "2026-10-27T12:00:00Z"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out) == {
        "available": True,
        "tz": "America/New_York",
        "local_now": "2026-10-27T08:00:00-04:00",
        "local_date": "2026-10-27",
    }
    assert database.read_bytes() == before
