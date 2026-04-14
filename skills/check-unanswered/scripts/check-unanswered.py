#!/usr/bin/env python3
"""
Deterministic unanswered message detector.

A user message is "handled" if either:
  1. A bot message exists with reply_to_message_id pointing to it, OR
  2. The bot already reacted to it (previous heartbeat processed it)

Outputs JSON to stdout. Empty list = nothing to report.
"""

import sqlite3
import json
import sys
import os
from datetime import datetime, timedelta, timezone

DB = os.environ.get('NANOCLAW_DB', '/workspace/store/messages.db')
CHAT_JID = os.environ.get('NANOCLAW_CHAT_JID', '')
LOOKBACK_HOURS = int(os.environ.get('LOOKBACK_HOURS', '24'))

if not CHAT_JID:
    # NANOCLAW_CHAT_JID must be set. Without it, the script cannot
    # determine which group to check. The previous fallback (most
    # recent bot message) was removed because it could select the
    # wrong group when the DB contains messages from multiple chats.
    print(json.dumps({
        "unanswered": [],
        "chat_jid": "",
        "error": "NANOCLAW_CHAT_JID not set — required env var.",
        "lookback_hours": LOOKBACK_HOURS,
        "checked_at": datetime.now(timezone.utc).isoformat()
    }))
    sys.exit(0)

try:
    conn = sqlite3.connect(DB, timeout=5)
except sqlite3.OperationalError as e:
    print(json.dumps({"unanswered": [], "error": f"DB open failed: {e}"}))
    sys.exit(0)

cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime('%Y-%m-%dT%H:%M:%S')

# Find user messages that have no bot reply AND no bot reaction.
# A message is "handled" if either:
#   1. A bot message exists with reply_to_message_id pointing to it, OR
#   2. The bot already reacted to it (meaning a previous heartbeat processed it)
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

conn.close()

results = [
    {"id": msg_id, "sender_name": sender, "content": content, "timestamp": ts}
    for msg_id, sender, content, ts in unanswered
]

print(json.dumps({
    "unanswered": results,
    "chat_jid": CHAT_JID,
    "lookback_hours": LOOKBACK_HOURS,
    "checked_at": datetime.now(timezone.utc).isoformat()
}))
