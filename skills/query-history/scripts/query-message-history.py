#!/usr/bin/env python3
"""
Query messages.db for the current chat by keyword and/or sender.

Invoked from `rules/context-recovery.md` when the agent is about to
claim lost context. Replaces the inlined Python snippet that lived in
the rule body — extraction tracked in jbaruch/nanoclaw-admin#181 (umbrella
RULES.md diet jbaruch/nanoclaw-admin#180).

Per `.github/copilot-instructions.md`, the on-tier invocation path is
`/home/node/.claude/skills/tessl__query-history/scripts/query-message-history.py`.

Usage:
    python3 .../query-message-history.py --keyword "release plan"
    python3 .../query-message-history.py --sender ligolnik
    python3 .../query-message-history.py --keyword "JCON" --sender ligolnik --limit 50
    python3 .../query-message-history.py --keyword "JCON" --limit 50 --offset 50

Env vars:
    NANOCLAW_CHAT_JID — required. Scopes the query to the current chat.
    NANOCLAW_DB       — optional, default `/workspace/store/messages.db`.

Output (stdout, single-line JSON):
    {
      "rows": [
        {"id", "timestamp", "sender_name", "content", "is_from_me",
         "content_truncated"},
        ...
      ],
      "chat_jid": str,
      "query": {"keyword": str|null, "sender": str|null, "limit": int,
                "offset": int},
      "truncated": bool,
      "rows_dropped": int,
      "error": str|null
    }

    The serialized payload is capped at MAX_OUTPUT_BYTES on every
    JSON-emitting path (success and error) so the result honors the
    25 KB single-tool-result budget from `rules/query-size-limits.md`.
    When the cap engages: each row's `content` is first clipped to
    PER_ROW_CONTENT_CHARS (that row's `content_truncated` flips true),
    then whole rows are dropped oldest-first (`rows_dropped` counts
    them, `truncated` flips true). Envelope strings (query echoes,
    error) clip to ENVELOPE_FIELD_CHARS so the zero-row envelope is
    bounded too. Re-query with narrower filters or `--offset` batches
    to see what was cut.

Exit codes:
    0 — clean success (rows may be empty).
    1 — runtime failure (NANOCLAW_CHAT_JID missing, DB access failure,
        sqlite error). Diagnostic on stderr, empty-rows JSON on stdout.
    2 — usage error: no --keyword AND no --sender, or --limit non-
        positive, or --limit above the 50-row messages.db cap from
        `rules/query-size-limits.md`, or --offset negative.
"""

import argparse
import json
import os
import sqlite3
import sys
from typing import Optional

DEFAULT_DB = "/workspace/store/messages.db"
DEFAULT_LIMIT = 20
# Hard cap mirrors `rules/query-size-limits.md` (max 50 rows for messages.db).
# Anything above this defeats the context-budget guard the rule set enforces.
MAX_LIMIT = 50
# Serialized-output budget mirrors the 25 KB single-tool-result limit in
# `rules/query-size-limits.md`. The row cap alone doesn't enforce it — a
# handful of long messages can blow the budget at 50 rows.
MAX_OUTPUT_BYTES = 25 * 1024
# Per-row content clip applied before whole rows are dropped: favors
# breadth (more rows, each capped) over depth (few complete rows). Chat
# messages are rarely this long; pasted logs and forwarded walls of text
# are the case this guards.
PER_ROW_CONTENT_CHARS = 4000
# Clip for envelope strings echoed into every payload (query.keyword,
# query.sender, error). Bounds the zero-row envelope so cap_payload's
# row-dropping loop can always land under MAX_OUTPUT_BYTES — a
# pathological multi-KB --keyword would otherwise bust the budget with
# no rows left to drop.
ENVELOPE_FIELD_CHARS = 500
LIKE_ESCAPE_CHAR = "\\"


def escape_like(value: str) -> str:
    """Make user input safe to interpolate as a LIKE pattern fragment.

    SQLite's `LIKE` treats `%` and `_` inside bound values as wildcards even
    with parameter binding — `?` only escapes SQL-syntax characters, not
    pattern metacharacters. So `--keyword 'john_doe'` would still match
    `johnXdoe`, defeating "literal context recovery". Escape both
    metacharacters (and the escape char itself) and pair the LIKE with an
    explicit `ESCAPE '\\\\'` clause in the query.
    """
    return (
        value.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
        .replace("%", LIKE_ESCAPE_CHAR + "%")
        .replace("_", LIKE_ESCAPE_CHAR + "_")
    )


def build_query(has_keyword: bool, has_sender: bool) -> str:
    """Compose the SELECT.

    Both filters are optional, but at least one must be set (caller-enforced).
    Keyword binds to `content`, sender binds to `sender_name` — the two are
    AND-combined when both are present, narrowing the result to messages
    matching both. Wildcards inside the bound value are escaped via
    `escape_like` + `ESCAPE '\\\\'` so user input matches literally.
    """
    where = ["chat_jid = ?"]
    if has_keyword:
        where.append("content LIKE '%' || ? || '%' ESCAPE '\\'")
    if has_sender:
        where.append("sender_name LIKE '%' || ? || '%' ESCAPE '\\'")
    return f"""
        SELECT id, timestamp, sender_name, content, is_from_me
        FROM messages
        WHERE {' AND '.join(where)}
        ORDER BY timestamp DESC, id DESC
        LIMIT ? OFFSET ?
    """


def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search messages.db for the current chat.",
    )
    parser.add_argument("--keyword", help="Substring to match against `content`.")
    parser.add_argument(
        "--sender",
        help="Substring to match against `sender_name` (matches both display "
        "name and `@username` since the column stores `Display (@username)`).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max rows to return (default {DEFAULT_LIMIT}).",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Rows to skip before returning results (default 0). Batch "
        "through result sets larger than the row cap with successive "
        "--offset values per rules/query-size-limits.md.",
    )
    return parser.parse_args(argv)


def make_payload(
    rows: list,
    chat_jid: str,
    keyword: Optional[str],
    sender: Optional[str],
    limit: int,
    offset: int,
    error: Optional[str],
) -> dict:
    """Single canonical output shape — every key present on success and
    error paths so the agent (or a downstream consumer) doesn't have to
    special-case error JSON. Envelope strings clip to
    ENVELOPE_FIELD_CHARS so the zero-row envelope stays bounded on
    every path (see cap_payload)."""

    def clip(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value[:ENVELOPE_FIELD_CHARS]

    return {
        "rows": rows,
        "chat_jid": chat_jid,
        "query": {
            "keyword": clip(keyword),
            "sender": clip(sender),
            "limit": limit,
            "offset": offset,
        },
        "truncated": False,
        "rows_dropped": 0,
        "error": clip(error),
    }


def cap_payload(payload: dict, max_bytes: int = MAX_OUTPUT_BYTES) -> dict:
    """Enforce the serialized-output budget in place.

    Phase 1 clips each row's `content` to PER_ROW_CONTENT_CHARS (marking
    that row's `content_truncated`). Phase 2 drops whole rows oldest-first
    (rows are ordered newest-first, so pops come off the tail) until the
    single-line JSON fits `max_bytes`, counting them in `rows_dropped`.
    Either phase engaging flips the top-level `truncated` flag. A payload
    already under budget passes through with only Phase-1 marking applied
    when a row exceeds the per-row clip."""

    def size(p: dict) -> int:
        # +1 for the trailing newline print() appends — the budget bounds
        # the full stdout tool result, not just the JSON body.
        return len(json.dumps(p).encode("utf-8")) + 1

    for row in payload["rows"]:
        content = row.get("content") or ""
        if len(content) > PER_ROW_CONTENT_CHARS:
            row["content"] = content[:PER_ROW_CONTENT_CHARS]
            row["content_truncated"] = True
            payload["truncated"] = True

    while payload["rows"] and size(payload) > max_bytes:
        payload["rows"].pop()
        payload["rows_dropped"] += 1
        payload["truncated"] = True

    return payload


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if not args.keyword and not args.sender:
        sys.stderr.write("Usage error: provide at least one of --keyword or --sender.\n")
        return 2

    if args.limit <= 0:
        sys.stderr.write(
            f"Usage error: --limit={args.limit} is non-positive; use a positive integer.\n"
        )
        return 2
    if args.limit > MAX_LIMIT:
        sys.stderr.write(
            f"Usage error: --limit={args.limit} exceeds the messages.db cap of "
            f"{MAX_LIMIT} rows (rules/query-size-limits.md). "
            f"Re-run with a smaller limit; batch through larger result sets "
            f"with successive --offset values.\n"
        )
        return 2
    if args.offset < 0:
        sys.stderr.write(
            f"Usage error: --offset={args.offset} is negative; use zero or a "
            f"positive integer.\n"
        )
        return 2

    chat_jid = os.environ.get("NANOCLAW_CHAT_JID", "")
    if not chat_jid:
        err = "NANOCLAW_CHAT_JID not set — required env var for chat scope."
        sys.stderr.write(err + "\n")
        print(
            json.dumps(
                cap_payload(
                    make_payload([], "", args.keyword, args.sender, args.limit, args.offset, err)
                )
            )
        )
        return 1

    db_path = os.environ.get("NANOCLAW_DB", DEFAULT_DB)
    sql = build_query(bool(args.keyword), bool(args.sender))
    params: list = [chat_jid]
    if args.keyword:
        params.append(escape_like(args.keyword))
    if args.sender:
        params.append(escape_like(args.sender))
    params.append(args.limit)
    params.append(args.offset)

    # Open the DB read-only via URI — `sqlite3.connect(path)` would otherwise
    # create an empty file at a missing/mistyped NANOCLAW_DB and silently
    # fail with `no such table` later, masking the misconfiguration and
    # leaving a bogus DB file on disk.
    db_uri = "file:" + db_path + "?mode=ro"
    conn = None
    try:
        conn = sqlite3.connect(db_uri, timeout=5, uri=True)
        cursor = conn.execute(sql, params)
        rows = [
            {
                "id": r[0],
                "timestamp": r[1],
                "sender_name": r[2],
                "content": r[3],
                "is_from_me": bool(r[4]),
                "content_truncated": False,
            }
            for r in cursor.fetchall()
        ]
    except sqlite3.Error as e:
        err = f"DB access failed: {e}"
        sys.stderr.write(err + "\n")
        print(
            json.dumps(
                cap_payload(
                    make_payload(
                        [], chat_jid, args.keyword, args.sender, args.limit, args.offset, err
                    )
                )
            )
        )
        return 1
    finally:
        if conn is not None:
            conn.close()

    payload = cap_payload(
        make_payload(rows, chat_jid, args.keyword, args.sender, args.limit, args.offset, None)
    )
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
