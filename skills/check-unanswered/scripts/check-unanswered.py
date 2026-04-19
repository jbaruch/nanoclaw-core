#!/usr/bin/env python3
"""
Two-phase unanswered message detector.

Phase 1 (deterministic SQL): find user messages that have neither a
threaded bot reply nor a bot reaction. Fast, cheap, no LLM.

Phase 2 (LLM-assisted, in the skill): for each candidate, reason over
the conversation between that message and now to decide whether the
bot already addressed it inline (without using reply_to_message_id or
reacting). Phase 2 lives in the skill workflow, not in this script —
scripts can't do "did this bot message substantively respond to that
user message" reliably, and the phrasing of the question is exactly
what LLMs are for.

Output shape (same on success AND on error paths, so downstream
consumers can parse/log uniformly):
  {
    "unanswered": [ {id, sender_name, content, timestamp}, ... ],
    "conversation_since": [ {id, sender_name, content, timestamp,
                             from_bot, reply_to_id}, ... ],
    "chat_jid": str,
    "lookback_hours": int,
    "context_cap": int,
    "checked_at": ISO-8601,
    "error": str,     # present only when something went wrong
  }

`unanswered` is the Phase-1 candidate set (same as before).
`conversation_since` is a chronologically-ordered, deduplicated union
of two slices: the first CONTEXT_CAP/2 messages from the EARLIEST
candidate onward, and the first CONTEXT_CAP/2 messages from the LATEST
candidate onward. For the typical case (candidates close together,
heartbeat running regularly) the slices overlap and dedup to the
expected contiguous window. For the edge case (multiple candidates
spread across a big high-volume window, e.g. a skipped heartbeat),
the split guarantees Phase 2 still sees each candidate's immediate
aftermath — which is where the inline answer, if any, almost always
lives. A final hard cap at `CONTEXT_CAP` keeps
`len(conversation_since) <= context_cap` as a firm invariant; when
the two slices union to more than the cap (possible with very spread
candidates), the LATEST rows win — that's where the inline answer
would land. CONTEXT_CAP defaults to 200.
"""

import sqlite3
import json
import sys
import os
from datetime import datetime, timedelta, timezone

DB = os.environ.get('NANOCLAW_DB', '/workspace/store/messages.db')
CHAT_JID = os.environ.get('NANOCLAW_CHAT_JID', '')


def _parse_int_env(name: str, default: int) -> tuple[int, str | None]:
    """Parse an integer env var, returning (value, error). On invalid
    input we fall back to `default` AND surface the original input in
    the error string so the caller can emit it to stderr — without
    this, a misconfigured `LOOKBACK_HOURS=abc` would crash the script
    with a traceback on stdout, breaking the "uniform JSON output
    shape on error paths" guarantee."""
    raw = os.environ.get(name)
    if raw is None or raw == '':
        return default, None
    try:
        return int(raw), None
    except ValueError:
        return default, f"{name}={raw!r} is not an integer; using default {default}"


LOOKBACK_HOURS, _LB_ERR = _parse_int_env('LOOKBACK_HOURS', 24)
CONTEXT_CAP, _CC_ERR = _parse_int_env('CONTEXT_CAP', 200)
# Clamp non-positive CONTEXT_CAP up to 1 so downstream slicing stays
# sensible (Python's negative-index semantics would otherwise turn
# `context_rows[-0:]` into "keep everything" and `context_rows[-(-5):]`
# into "skip 5 from the front, keep the rest" — both surprising).
# Setting CONTEXT_CAP=0 to silence the context window is rare enough
# that saving one query isn't worth carrying an `if cap == 0` branch
# through the whole flow.
if CONTEXT_CAP < 1:
    _CC_ERR = (
        (_CC_ERR + ' | ' if _CC_ERR else '')
        + f"CONTEXT_CAP={CONTEXT_CAP} is non-positive; clamping to 1"
    )
    CONTEXT_CAP = 1
_env_errors = [e for e in (_LB_ERR, _CC_ERR) if e]
if _env_errors:
    # Warn but don't fail — the defaults are safe and the script still
    # produces useful output. Surface via stderr so operators see it in
    # the precheck's error-wake payload.
    sys.stderr.write(" | ".join(_env_errors) + "\n")

def _empty_payload(error: str):
    """Return the same shape as the success path so downstream consumers
    don't have to special-case error JSON. Every key the happy path
    emits is present here; `error` is the only extra."""
    return {
        "unanswered": [],
        "conversation_since": [],
        "chat_jid": CHAT_JID,
        "lookback_hours": LOOKBACK_HOURS,
        "context_cap": CONTEXT_CAP,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }


if not CHAT_JID:
    # NANOCLAW_CHAT_JID must be set. Without it, the script cannot
    # determine which group to check. The previous fallback (most
    # recent bot message) was removed because it could select the
    # wrong group when the DB contains messages from multiple chats.
    #
    # Exit non-zero so callers that check the process exit code (e.g.
    # unanswered-precheck.py's `if result.returncode != 0: wake agent`)
    # surface the misconfig instead of treating it as "no unanswered
    # messages, nothing to do." Also emit the same message to stderr —
    # the precheck wraps stderr into its wake-data payload, so operators
    # see the actual reason for the wake instead of an opaque empty
    # string.
    err = "NANOCLAW_CHAT_JID not set — required env var."
    sys.stderr.write(err + "\n")
    print(json.dumps(_empty_payload(err)))
    sys.exit(1)

try:
    conn = sqlite3.connect(DB, timeout=5)
except sqlite3.OperationalError as e:
    # DB access failure is also a hard problem worth waking someone for,
    # not a silent "zero orphans" answer.
    err = f"DB open failed: {e}"
    sys.stderr.write(err + "\n")
    print(json.dumps(_empty_payload(err)))
    sys.exit(1)

cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime('%Y-%m-%dT%H:%M:%S')

# Phase 1: find user messages with no bot reply AND no bot reaction.
# A message is "handled" if either:
#   1. A bot message exists with reply_to_message_id pointing to it, OR
#   2. The bot already reacted to it (previous heartbeat marked it
#      addressed inline via Phase 2 reasoning).
#
# The "bot message" predicate accepts EITHER flag:
#   - `r.is_from_me = 1` covers main-bot sends (the orchestrator's
#     primary Telegram identity).
#   - `r.is_bot_message = 1` covers pool-bot sends (agent-swarm bots
#     operating under a per-sender identity; written by the
#     orchestrator's `sendPoolMessage` code path).
# A narrower check that only matched `is_from_me = 1` missed pool-bot
# threaded replies, so the main-bot + pool-bot mix would resurface
# already-answered messages as candidates.
unanswered = conn.execute("""
    SELECT m.id, m.sender_name, m.content, m.timestamp
    FROM messages m
    WHERE m.chat_jid = ?
      AND m.is_from_me = 0
      AND m.is_bot_message = 0
      AND m.timestamp > ?
      AND NOT EXISTS (
        SELECT 1 FROM messages r
        WHERE r.chat_jid = m.chat_jid
          AND (r.is_from_me = 1 OR r.is_bot_message = 1)
          AND r.reply_to_message_id = m.id
      )
      AND NOT EXISTS (
        SELECT 1 FROM reactions rc
        WHERE rc.message_id = m.id
          AND rc.message_chat_jid = m.chat_jid
          AND rc.reactor_jid = 'bot@telegram'
      )
    ORDER BY m.timestamp ASC
""", (CHAT_JID, cutoff)).fetchall()

results = [
    {"id": msg_id, "sender_name": sender, "content": content, "timestamp": ts}
    for msg_id, sender, content, ts in unanswered
]

# Phase 2 context: a bounded window of chat messages around the
# candidates (see the two-slice strategy below). The skill reads this
# to decide per-candidate "did a subsequent bot message address this
# inline?" — without the context, there's no reasoning possible and
# the skill degrades to blind reply-to-every-candidate, which is
# exactly the duplicate-answer bug this script exists to avoid.
if results:
    earliest_orphan_ts = results[0]["timestamp"]
    latest_orphan_ts = results[-1]["timestamp"]
    # Two-slice context window:
    #   - HEAD: first N/2 messages from the earliest candidate onward.
    #     Covers the first candidate's immediate aftermath, where an
    #     inline answer (if any) almost always lives.
    #   - TAIL: first N/2 messages from the latest candidate onward.
    #     Covers the latest candidate's immediate aftermath.
    # When candidates are close together (typical heartbeat case) the
    # two slices overlap and dedup collapses them. When candidates are
    # spread across a high-volume chat window (e.g. heartbeat was
    # skipped for hours), the split guarantees each candidate still
    # has its "did the bot answer this?" context visible to Phase 2 —
    # a single monolithic "first N since earliest" query would drop
    # later candidates' context whenever >N messages happened between
    # the earliest and the latest.
    # Half-cap per slice, floored at 1 so CONTEXT_CAP=1 still fetches
    # something. The final `context_rows[-CONTEXT_CAP:]` slice below is
    # the hard cap that keeps `len(conversation_since) <= context_cap`
    # invariant — this floor is only about making each slice non-empty.
    slice_cap = max(CONTEXT_CAP // 2, 1)
    head_rows = conn.execute(
        """
        SELECT id, sender_name, content, timestamp, is_from_me, is_bot_message, reply_to_message_id
        FROM messages
        WHERE chat_jid = ?
          AND timestamp >= ?
        ORDER BY timestamp ASC
        LIMIT ?
        """,
        (CHAT_JID, earliest_orphan_ts, slice_cap),
    ).fetchall()
    tail_rows = conn.execute(
        """
        SELECT id, sender_name, content, timestamp, is_from_me, is_bot_message, reply_to_message_id
        FROM messages
        WHERE chat_jid = ?
          AND timestamp >= ?
        ORDER BY timestamp ASC
        LIMIT ?
        """,
        (CHAT_JID, latest_orphan_ts, slice_cap),
    ).fetchall()
    # Dedup by id, preserve chronological order.
    seen_ids = set()
    context_rows = []
    for r in head_rows + tail_rows:
        if r[0] in seen_ids:
            continue
        seen_ids.add(r[0])
        context_rows.append(r)
    # Stable tie-break by id when timestamps collide. SQLite message
    # timestamps are second-precision in some paths, and two messages
    # that arrive within the same second will both sort-compare equal
    # on the timestamp alone. Python's sort is stable, but insertion
    # order here comes from head+tail concatenation — not useful for
    # Phase 2. Pairing `(ts, id)` gives deterministic order across
    # runs regardless of how the rows were fetched.
    context_rows.sort(key=lambda r: (r[3], r[0]))
    # Final hard cap at CONTEXT_CAP. `slice_cap = max(CONTEXT_CAP//2,
    # 50)` keeps each slice useful, but when CONTEXT_CAP is overridden
    # low (e.g. 20) the head+tail unioned total can exceed the
    # configured cap — which contradicts what `context_cap` reports.
    # Clip here so `len(conversation_since) <= context_cap` always
    # holds, and Phase 2's token/cost budget matches the operator's
    # intent. Keep the LATEST messages on tie (slicing by `[-cap:]`)
    # — they're the ones most likely to contain an inline answer.
    if len(context_rows) > CONTEXT_CAP:
        context_rows = context_rows[-CONTEXT_CAP:]
    conversation_since = [
        {
            "id": r[0],
            "sender_name": r[1],
            "content": r[2],
            "timestamp": r[3],
            # A message is "from the bot" if either flag is set — older
            # rows set `is_from_me=1` for the main-bot identity while
            # pool-bot sends set `is_bot_message=1`. Unified here so the
            # skill doesn't have to know which column applies.
            "from_bot": bool(r[4]) or bool(r[5]),
            "reply_to_id": r[6],
        }
        for r in context_rows
    ]
else:
    conversation_since = []

conn.close()

print(json.dumps({
    "unanswered": results,
    "conversation_since": conversation_since,
    "chat_jid": CHAT_JID,
    "lookback_hours": LOOKBACK_HOURS,
    "context_cap": CONTEXT_CAP,
    "checked_at": datetime.now(timezone.utc).isoformat()
}))
