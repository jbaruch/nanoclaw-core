"""Tests for skills/query-history/scripts/query-message-history.py.

Coverage:
  - argument validation (no filters, non-positive limit, over-cap limit,
    negative offset)
  - missing NANOCLAW_CHAT_JID returns exit 1 with canonical payload
  - keyword-only / sender-only / combined filters return matching rows
  - LIKE wildcard escape (`%` and `_` in user input match literally,
    not as wildcards) — verified via near-miss fixture rows
  - --offset pages past earlier rows in timestamp-DESC order
  - output-size cap: per-row content clip (content_truncated) and
    oldest-first row drops (rows_dropped) keep the serialized payload
    within MAX_OUTPUT_BYTES
  - DB-access failure returns exit 1 with canonical payload
  - payload shape consistency

The fixture loads the script as a module per test (per-test reload so
env mutations don't leak), then we drive `main()` directly with a
stubbed `argv` list and a real on-disk SQLite DB redirected via
NANOCLAW_DB.
"""

import io
import json
import sqlite3
from contextlib import redirect_stderr, redirect_stdout

import pytest


def _populate_db(path: str) -> None:
    """Build a tiny fixed dataset deterministically.

    Two chats, three senders. Values chosen so that filters narrow
    predictably and tie-break ordering can be asserted on timestamp
    DESC."""
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            chat_jid TEXT,
            sender_name TEXT,
            content TEXT,
            timestamp TEXT,
            is_from_me INTEGER
        )"""
    )
    rows = [
        (1, "chatA", "Alice (@alice)", "release plan for Q3", "2026-01-01T10:00:00", 0),
        (2, "chatA", "Bob (@bob)", "release plan looks good", "2026-01-02T10:00:00", 0),
        (3, "chatA", "Alice (@alice)", "unrelated chat", "2026-01-03T10:00:00", 0),
        (4, "chatB", "Alice (@alice)", "release plan in other chat", "2026-01-04T10:00:00", 0),
        (5, "chatA", "Bot (@bot)", "replying to release", "2026-01-05T10:00:00", 1),
        # Two near-miss rows that exercise LIKE-wildcard escape:
        #   id=6 has a literal underscore — `--keyword 'john_doe'` MUST match
        #     this and nothing else.
        #   id=7 has the same letters with `X` between them; without escape,
        #     `_` in the bound value is a wildcard and id=7 ALSO matches.
        # The escape contract is verified by asserting id=6 matches and id=7
        # does not.
        (6, "chatA", "Alice (@alice)", "ping from john_doe today", "2026-01-06T10:00:00", 0),
        (7, "chatA", "Alice (@alice)", "ping from johnXdoe today", "2026-01-07T10:00:00", 0),
    ]
    conn.executemany(
        "INSERT INTO messages "
        "(id, chat_jid, sender_name, content, timestamp, is_from_me) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def _run(
    module,
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    db_path: str | None = None,
    chat_jid: str | None = "chatA",
) -> tuple[int, dict | None, str]:
    """Invoke `main(argv)` with env vars set, capturing stdout/stderr.

    Returns (exit_code, parsed_stdout_payload_or_None, stderr_text).
    Stdout is parsed if non-empty; usage-error paths exit before
    printing JSON, so callers receive `None` for those."""
    if db_path:
        monkeypatch.setenv("NANOCLAW_DB", db_path)
    if chat_jid is None:
        monkeypatch.delenv("NANOCLAW_CHAT_JID", raising=False)
    else:
        monkeypatch.setenv("NANOCLAW_CHAT_JID", chat_jid)

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = module.main(argv)
    stdout = out.getvalue()
    payload = json.loads(stdout) if stdout.strip() else None
    return rc, payload, err.getvalue()


def _require_payload(payload: dict | None) -> dict:
    """Narrow a `_run` payload to a present dict for tests on the success
    and canonical-error paths, which always print a JSON payload. Usage-error
    paths return None and must not call this."""
    if payload is None:
        raise AssertionError("expected a JSON payload but stdout was empty")
    return payload


def test_no_filters_is_usage_error(query_message_history, monkeypatch):
    rc, payload, stderr = _run(query_message_history, [], monkeypatch)
    assert rc == 2
    assert payload is None
    assert "at least one of --keyword or --sender" in stderr


def test_non_positive_limit_is_usage_error(query_message_history, monkeypatch):
    rc, payload, stderr = _run(
        query_message_history, ["--keyword", "x", "--limit", "0"], monkeypatch
    )
    assert rc == 2
    assert payload is None
    assert "--limit=0" in stderr


def test_limit_above_messages_db_cap_is_usage_error(query_message_history, monkeypatch):
    # `rules/query-size-limits.md` caps `messages.db` queries at 50 rows.
    # The script must reject anything above that to keep the rule
    # enforceable from the tooling side, not just the prose side.
    rc, payload, stderr = _run(
        query_message_history, ["--keyword", "x", "--limit", "51"], monkeypatch
    )
    assert rc == 2
    assert payload is None
    assert "--limit=51" in stderr
    assert "50 rows" in stderr
    assert "query-size-limits" in stderr


def test_limit_at_messages_db_cap_is_accepted(query_message_history, monkeypatch, tmp_path):
    # Boundary check: exactly the cap (50) is allowed; only 51+ rejects.
    db_path = str(tmp_path / "db.sqlite")
    _populate_db(db_path)
    rc, _payload, _stderr = _run(
        query_message_history,
        ["--keyword", "release", "--limit", "50"],
        monkeypatch,
        db_path=db_path,
    )
    assert rc == 0


def test_missing_chat_jid_returns_canonical_error(query_message_history, monkeypatch, tmp_path):
    db_path = str(tmp_path / "db.sqlite")
    _populate_db(db_path)
    rc, payload, stderr = _run(
        query_message_history,
        ["--keyword", "release"],
        monkeypatch,
        db_path=db_path,
        chat_jid=None,
    )
    assert rc == 1
    assert "NANOCLAW_CHAT_JID" in stderr
    payload = _require_payload(payload)
    assert payload["rows"] == []
    assert payload["error"].startswith("NANOCLAW_CHAT_JID")
    assert payload["query"] == {"keyword": "release", "sender": None, "limit": 20, "offset": 0}


def test_keyword_filter_returns_matching_rows_in_chat(query_message_history, monkeypatch, tmp_path):
    db_path = str(tmp_path / "db.sqlite")
    _populate_db(db_path)
    rc, payload, _ = _run(
        query_message_history,
        ["--keyword", "release plan"],
        monkeypatch,
        db_path=db_path,
    )
    assert rc == 0
    payload = _require_payload(payload)
    contents = [r["content"] for r in payload["rows"]]
    # Two chatA messages contain 'release plan'; chatB row is excluded.
    # Also excluded: 'replying to release' (different substring),
    # 'unrelated chat' (no match).
    assert contents == ["release plan looks good", "release plan for Q3"]
    # DESC ordering on timestamp.
    assert payload["rows"][0]["timestamp"] > payload["rows"][1]["timestamp"]
    assert payload["error"] is None


def test_sender_filter_uses_sender_name_substring(query_message_history, monkeypatch, tmp_path):
    db_path = str(tmp_path / "db.sqlite")
    _populate_db(db_path)
    rc, payload, _ = _run(
        query_message_history,
        ["--sender", "alice"],
        monkeypatch,
        db_path=db_path,
    )
    assert rc == 0
    payload = _require_payload(payload)
    # Four chatA rows where sender_name LIKE '%alice%' (ids 1, 3, 6, 7).
    # The chatB alice row (id=4) is excluded by the chat_jid filter.
    senders = {r["sender_name"] for r in payload["rows"]}
    assert senders == {"Alice (@alice)"}
    assert len(payload["rows"]) == 4


def test_combined_filters_AND(query_message_history, monkeypatch, tmp_path):
    db_path = str(tmp_path / "db.sqlite")
    _populate_db(db_path)
    rc, payload, _ = _run(
        query_message_history,
        ["--keyword", "release plan", "--sender", "alice"],
        monkeypatch,
        db_path=db_path,
    )
    assert rc == 0
    payload = _require_payload(payload)
    # Alice has two release-plan-substring rows in chatA: id=1 ('release
    # plan for Q3') is the only one that matches 'release plan' AND
    # alice. id=2 is Bob.
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["id"] == 1


def test_keyword_underscore_wildcard_is_escaped(query_message_history, monkeypatch, tmp_path):
    db_path = str(tmp_path / "db.sqlite")
    _populate_db(db_path)
    # Without LIKE-wildcard escape, the bound value `john_doe` makes the
    # underscore act as "match any single character" — `johnXdoe`
    # (id=7) would also match. With escape (`escape_like` +
    # `ESCAPE '\\'`), only the literal `john_doe` row (id=6) returns.
    # This is the contract; failing the assert means the script would
    # over-match user-supplied search terms containing `%` or `_`.
    rc, payload, _ = _run(
        query_message_history,
        ["--keyword", "john_doe"],
        monkeypatch,
        db_path=db_path,
    )
    assert rc == 0
    payload = _require_payload(payload)
    ids = sorted(r["id"] for r in payload["rows"])
    assert ids == [6], (
        f"Expected only id=6 (literal `john_doe`), got {ids}. "
        f"id=7 in the fixture is `johnXdoe`; if it appears, the LIKE "
        f"wildcard `_` is not being escaped."
    )


def test_keyword_percent_wildcard_is_escaped(query_message_history, monkeypatch, tmp_path):
    db_path = str(tmp_path / "db.sqlite")
    _populate_db(db_path)
    # `%doe` — without escape, `%` in the bound value is "match
    # anything", so any row containing `doe` matches. With escape,
    # only rows containing the literal substring `%doe` match — and
    # the fixture has none, so the result is empty.
    rc, payload, _ = _run(
        query_message_history,
        ["--keyword", "%doe"],
        monkeypatch,
        db_path=db_path,
    )
    assert rc == 0
    payload = _require_payload(payload)
    assert payload["rows"] == [], (
        f"Expected empty result for literal `%doe` (no row contains it), "
        f"got {[r['id'] for r in payload['rows']]}. The `%` wildcard is "
        f"not being escaped."
    )


def test_limit_caps_results(query_message_history, monkeypatch, tmp_path):
    db_path = str(tmp_path / "db.sqlite")
    _populate_db(db_path)
    rc, payload, _ = _run(
        query_message_history,
        ["--sender", "alice", "--limit", "2"],
        monkeypatch,
        db_path=db_path,
    )
    assert rc == 0
    payload = _require_payload(payload)
    assert len(payload["rows"]) == 2
    assert payload["query"]["limit"] == 2


def test_db_missing_returns_canonical_error(query_message_history, monkeypatch, tmp_path):
    # Non-existent DB path. Script opens via `file:…?mode=ro`, so a
    # missing/mistyped path fails fast at connect rather than silently
    # creating an empty DB. The canonical error payload + non-zero
    # exit must still be emitted.
    bogus = tmp_path / "no-such-db.sqlite"
    rc, payload, stderr = _run(
        query_message_history,
        ["--keyword", "x"],
        monkeypatch,
        db_path=str(bogus),
    )
    assert rc == 1
    assert "DB access failed" in stderr
    payload = _require_payload(payload)
    assert payload["rows"] == []
    assert payload["error"].startswith("DB access failed")


def test_payload_shape_is_canonical_on_success(query_message_history, monkeypatch, tmp_path):
    db_path = str(tmp_path / "db.sqlite")
    _populate_db(db_path)
    rc, payload, _ = _run(
        query_message_history,
        ["--keyword", "release"],
        monkeypatch,
        db_path=db_path,
    )
    assert rc == 0
    payload = _require_payload(payload)
    assert set(payload.keys()) == {
        "rows",
        "chat_jid",
        "query",
        "truncated",
        "rows_dropped",
        "error",
    }
    assert payload["chat_jid"] == "chatA"
    assert payload["truncated"] is False
    assert payload["rows_dropped"] == 0
    if payload["rows"]:
        assert set(payload["rows"][0].keys()) == {
            "id",
            "timestamp",
            "sender_name",
            "content",
            "is_from_me",
            "content_truncated",
        }
        assert isinstance(payload["rows"][0]["is_from_me"], bool)
        assert payload["rows"][0]["content_truncated"] is False


def test_negative_offset_is_usage_error(query_message_history, monkeypatch):
    rc, payload, stderr = _run(
        query_message_history, ["--keyword", "x", "--offset", "-1"], monkeypatch
    )
    assert rc == 2
    assert payload is None
    assert "--offset=-1" in stderr


def test_offset_batches_past_earlier_rows(query_message_history, monkeypatch, tmp_path):
    db_path = str(tmp_path / "db.sqlite")
    _populate_db(db_path)
    # Alice has four chatA rows (ids 7, 6, 3, 1 in timestamp-DESC order).
    # --limit 2 --offset 2 must return the third and fourth rows of that
    # ordering — the batch after the first --limit 2 page.
    rc, payload, _ = _run(
        query_message_history,
        ["--sender", "alice", "--limit", "2", "--offset", "2"],
        monkeypatch,
        db_path=db_path,
    )
    assert rc == 0
    payload = _require_payload(payload)
    ids = [r["id"] for r in payload["rows"]]
    assert ids == [3, 1], (
        f"Expected the second page (ids [3, 1]) of Alice's timestamp-DESC "
        f"rows, got {ids}. --offset is not being applied to the query."
    )
    assert payload["query"]["offset"] == 2


def test_offset_paging_is_deterministic_on_equal_timestamps(
    query_message_history, monkeypatch, tmp_path
):
    db_path = str(tmp_path / "db.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            chat_jid TEXT,
            sender_name TEXT,
            content TEXT,
            timestamp TEXT,
            is_from_me INTEGER
        )"""
    )
    # Four rows sharing ONE timestamp. ORDER BY timestamp alone leaves
    # their relative order undefined, so successive --offset pages could
    # duplicate or skip rows. The id DESC tie-breaker makes the total
    # order [4, 3, 2, 1]; two --limit 2 pages must partition it exactly.
    rows = [
        (i, "chatA", "Alice (@alice)", f"burst msg {i}", "2026-01-01T10:00:00", 0)
        for i in range(1, 5)
    ]
    conn.executemany("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    pages = []
    for offset in (0, 2):
        rc, payload, _ = _run(
            query_message_history,
            ["--keyword", "burst", "--limit", "2", "--offset", str(offset)],
            monkeypatch,
            db_path=db_path,
        )
        assert rc == 0
        pages.append([r["id"] for r in _require_payload(payload)["rows"]])
    assert pages == [[4, 3], [2, 1]], (
        f"Equal-timestamp rows must page deterministically via the id DESC "
        f"tie-breaker (expected [[4, 3], [2, 1]], got {pages}). Duplicated "
        f"or skipped ids mean the total order is undefined across pages."
    )


def test_error_path_payload_is_capped_too(query_message_history, monkeypatch):
    # A pathological multi-KB --keyword echoes into the payload on the
    # missing-NANOCLAW_CHAT_JID error path, which has zero rows to drop —
    # the envelope clip (ENVELOPE_FIELD_CHARS) must keep the output
    # within budget anyway.
    module = query_message_history
    giant_keyword = "k" * (3 * module.MAX_OUTPUT_BYTES)
    rc, payload, _stderr = _run(
        module,
        ["--keyword", giant_keyword],
        monkeypatch,
        chat_jid=None,
    )
    assert rc == 1
    payload = _require_payload(payload)
    raw = json.dumps(payload)
    assert len(raw.encode("utf-8")) <= module.MAX_OUTPUT_BYTES, (
        f"Error-path payload is {len(raw.encode('utf-8'))} bytes — exceeds "
        f"MAX_OUTPUT_BYTES ({module.MAX_OUTPUT_BYTES}). Error paths must "
        f"honor the tool-result budget too."
    )
    assert len(payload["query"]["keyword"]) == module.ENVELOPE_FIELD_CHARS
    # A clipped envelope field is a truncation — the flag must say so.
    assert payload["truncated"] is True


def test_oversized_content_is_clipped_per_row(query_message_history, monkeypatch, tmp_path):
    db_path = str(tmp_path / "db.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            chat_jid TEXT,
            sender_name TEXT,
            content TEXT,
            timestamp TEXT,
            is_from_me INTEGER
        )"""
    )
    # One row whose content exceeds the per-row clip: a 6000-char wall
    # around a matchable keyword.
    conn.execute(
        "INSERT INTO messages VALUES (1, 'chatA', 'Alice (@alice)', ?, '2026-01-01T10:00:00', 0)",
        ("wall " + "x" * 6000,),
    )
    conn.commit()
    conn.close()
    rc, payload, _ = _run(
        query_message_history,
        ["--keyword", "wall"],
        monkeypatch,
        db_path=db_path,
    )
    assert rc == 0
    payload = _require_payload(payload)
    module = query_message_history
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert len(row["content"]) == module.PER_ROW_CONTENT_CHARS, (
        f"Expected content clipped to PER_ROW_CONTENT_CHARS "
        f"({module.PER_ROW_CONTENT_CHARS}), got {len(row['content'])} chars."
    )
    assert row["content_truncated"] is True
    assert payload["truncated"] is True
    assert payload["rows_dropped"] == 0


def test_output_capped_to_budget_drops_oldest_rows(query_message_history, monkeypatch, tmp_path):
    db_path = str(tmp_path / "db.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            chat_jid TEXT,
            sender_name TEXT,
            content TEXT,
            timestamp TEXT,
            is_from_me INTEGER
        )"""
    )
    # 20 rows of ~3900 chars each: under the per-row clip, but ~78 KB
    # total — far over MAX_OUTPUT_BYTES. The cap must drop oldest rows
    # (lowest timestamps) and keep the newest.
    rows = [
        (
            i,
            "chatA",
            "Alice (@alice)",
            f"bigmsg {i:02d} " + "y" * 3890,
            f"2026-01-{i:02d}T10:00:00",
            0,
        )
        for i in range(1, 21)
    ]
    conn.executemany("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    rc, payload, _ = _run(
        query_message_history,
        ["--keyword", "bigmsg", "--limit", "20"],
        monkeypatch,
        db_path=db_path,
    )
    assert rc == 0
    payload = _require_payload(payload)
    module = query_message_history
    raw = json.dumps(payload)
    assert len(raw.encode("utf-8")) <= module.MAX_OUTPUT_BYTES, (
        f"Serialized payload is {len(raw.encode('utf-8'))} bytes — exceeds "
        f"MAX_OUTPUT_BYTES ({module.MAX_OUTPUT_BYTES}). The output cap is "
        f"not enforcing the rules/query-size-limits.md budget."
    )
    assert payload["truncated"] is True
    assert payload["rows_dropped"] > 0
    assert len(payload["rows"]) + payload["rows_dropped"] == 20
    # Newest-first ordering preserved; drops came off the oldest tail.
    kept_ids = [r["id"] for r in payload["rows"]]
    assert kept_ids == sorted(kept_ids, reverse=True)
    assert kept_ids[0] == 20, (
        f"Newest row (id=20) must survive the cap; kept ids: {kept_ids}. "
        f"Rows must drop oldest-first."
    )
