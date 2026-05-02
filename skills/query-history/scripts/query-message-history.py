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

Env vars:
    NANOCLAW_CHAT_JID — required. Scopes the query to the current chat.
    NANOCLAW_DB       — optional, default `/workspace/store/messages.db`.

Output (stdout, single-line JSON):
    {
      "rows": [
        {"id", "timestamp", "sender_name", "content", "is_from_me"},
        ...
      ],
      "chat_jid": str,
      "query": {"keyword": str|null, "sender": str|null, "limit": int},
      "error": str|null
    }

Exit codes:
    0 — clean success (rows may be empty).
    1 — runtime failure (NANOCLAW_CHAT_JID missing, DB access failure,
        sqlite error). Diagnostic on stderr, empty-rows JSON on stdout.
    2 — usage error: no --keyword AND no --sender, or --limit non-
        positive, or --limit above the 50-row messages.db cap from
        `rules/query-size-limits.md`.
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
        ORDER BY timestamp DESC
        LIMIT ?
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
    return parser.parse_args(argv)


def make_payload(
    rows: list,
    chat_jid: str,
    keyword: Optional[str],
    sender: Optional[str],
    limit: int,
    error: Optional[str],
) -> dict:
    """Single canonical output shape — every key present on success and
    error paths so the agent (or a downstream consumer) doesn't have to
    special-case error JSON."""
    return {
        "rows": rows,
        "chat_jid": chat_jid,
        "query": {"keyword": keyword, "sender": sender, "limit": limit},
        "error": error,
    }


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
            f"Re-run with a smaller limit or use OFFSET-based batching.\n"
        )
        return 2

    chat_jid = os.environ.get("NANOCLAW_CHAT_JID", "")
    if not chat_jid:
        err = "NANOCLAW_CHAT_JID not set — required env var for chat scope."
        sys.stderr.write(err + "\n")
        print(json.dumps(make_payload([], "", args.keyword, args.sender, args.limit, err)))
        return 1

    db_path = os.environ.get("NANOCLAW_DB", DEFAULT_DB)
    sql = build_query(bool(args.keyword), bool(args.sender))
    params: list = [chat_jid]
    if args.keyword:
        params.append(escape_like(args.keyword))
    if args.sender:
        params.append(escape_like(args.sender))
    params.append(args.limit)

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
            }
            for r in cursor.fetchall()
        ]
    except sqlite3.Error as e:
        err = f"DB access failed: {e}"
        sys.stderr.write(err + "\n")
        print(json.dumps(make_payload([], chat_jid, args.keyword, args.sender, args.limit, err)))
        return 1
    finally:
        if conn is not None:
            conn.close()

    print(json.dumps(make_payload(rows, chat_jid, args.keyword, args.sender, args.limit, None)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
