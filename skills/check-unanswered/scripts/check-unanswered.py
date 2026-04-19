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

Output shape:
  {
    "unanswered": [ {id, sender_name, content, timestamp}, ... ],
    "conversation_since": [ {id, sender_name, content, timestamp,
                             from_bot, reply_to_id}, ... ],
    "chat_jid": str,
    "lookback_hours": int,
    "checked_at": ISO-8601,
  }

`unanswered` is the Phase-1 candidate set (same as before).
`conversation_since` is every chat message from the earliest candidate's
timestamp up to now, chronologically, so the skill's Phase 2 reasoning
has the context to decide per-candidate "addressed inline" vs "truly
unanswered." Capped at 200 messages to keep the reasoning prompt sane
when a candidate has been sitting for hours; the cap picks the MOST
RECENT 200, so the bot messages that would plausibly contain the
inline answer are always in-window.
"""

import sqlite3
import json
import sys
import os
from datetime import datetime, timedelta, timezone

DB = os.environ.get('NANOCLAW_DB', '/workspace/store/messages.db')
CHAT_JID = os.environ.get('NANOCLAW_CHAT_JID', '')
LOOKBACK_HOURS = int(os.environ.get('LOOKBACK_HOURS', '24'))
CONTEXT_CAP = int(os.environ.get('CONTEXT_CAP', '200'))

if not CHAT_JID:
    # NANOCLAW_CHAT_JID must be set. Without it, the script cannot
    # determine which group to check. The previous fallback (most
    # recent bot message) was removed because it could select the
    # wrong group when the DB contains messages from multiple chats.
    print(json.dumps({
        "unanswered": [],
        "conversation_since": [],
        "chat_jid": "",
        "error": "NANOCLAW_CHAT_JID not set — required env var.",
        "lookback_hours": LOOKBACK_HOURS,
        "checked_at": datetime.now(timezone.utc).isoformat()
    }))
    sys.exit(0)

try:
    conn = sqlite3.connect(DB, timeout=5)
except sqlite3.OperationalError as e:
    print(json.dumps({"unanswered": [], "conversation_since": [], "error": f"DB open failed: {e}"}))
    sys.exit(0)

cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime('%Y-%m-%dT%H:%M:%S')

# Phase 1: find user messages with no bot reply AND no bot reaction.
# A message is "handled" if either:
#   1. A bot message exists with reply_to_message_id pointing to it, OR
#   2. The bot already reacted to it (previous heartbeat marked it
#      addressed inline via Phase 2 reasoning).
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
          AND r.is_from_me = 1
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

# Phase 2 context: every chat message from the earliest candidate's
# timestamp up to now. The skill reads this to decide per-candidate
# "did a subsequent bot message address this inline?" — without the
# context, there's no reasoning possible and the skill degrades to
# blind reply-to-every-candidate, which is exactly the duplicate-
# answer bug this script exists to avoid.
if results:
    earliest_orphan_ts = results[0]["timestamp"]
    # LIMIT clipping gotcha: we want the MOST RECENT N if there are
    # more than CONTEXT_CAP, because the inline answer (if any) is
    # near the bottom of the window, not near the top. Fetch
    # `ORDER BY timestamp DESC LIMIT N` then reverse in Python so the
    # skill reads the window chronologically.
    context_rows = conn.execute("""
        SELECT id, sender_name, content, timestamp, is_from_me, is_bot_message, reply_to_message_id
        FROM messages
        WHERE chat_jid = ?
          AND timestamp >= ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (CHAT_JID, earliest_orphan_ts, CONTEXT_CAP)).fetchall()
    context_rows.reverse()
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
