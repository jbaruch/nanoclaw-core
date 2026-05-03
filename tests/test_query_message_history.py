"""Tests for skills/query-history/scripts/query-message-history.py.

Coverage:
  - argument validation (no filters, non-positive limit, over-cap limit)
  - missing NANOCLAW_CHAT_JID returns exit 1 with canonical payload
  - keyword-only / sender-only / combined filters return matching rows
  - LIKE wildcard escape (`%` and `_` in user input match literally,
    not as wildcards) — verified via near-miss fixture rows
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


def _run(module, argv, monkeypatch, db_path=None, chat_jid="chatA"):
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
    assert payload["rows"] == []
    assert payload["error"].startswith("NANOCLAW_CHAT_JID")
    assert payload["query"] == {"keyword": "release", "sender": None, "limit": 20}


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
    assert set(payload.keys()) == {"rows", "chat_jid", "query", "error"}
    assert payload["chat_jid"] == "chatA"
    if payload["rows"]:
        assert set(payload["rows"][0].keys()) == {
            "id",
            "timestamp",
            "sender_name",
            "content",
            "is_from_me",
        }
        assert isinstance(payload["rows"][0]["is_from_me"], bool)
