---
alwaysApply: true
---

# Context Recovery — Never Lose History

## The Rule

**Never say you've lost context or forgotten a previous conversation without first querying `messages.db`.**

The full message history is always available at `/workspace/store/messages.db`. Context compaction removes it from your active context — but the database still has it. There is no excuse for "I don't remember what we discussed" when the database is a query away.

## Required behavior

Before responding with any variant of:
- "Потерял контекст"
- "I don't remember this thread"
- "What were we discussing?"
- "I don't have context on this topic"
- Any acknowledgment that prior conversation is unavailable

You **MUST** first run:

```python
import os, sqlite3
chat_jid = os.environ.get('NANOCLAW_CHAT_JID')
if not chat_jid:
    raise RuntimeError('NANOCLAW_CHAT_JID must be set — this snippet has to run in the agent container')
keyword = 'KEYWORD'  # replace with a relevant term from what the user is referencing
conn = sqlite3.connect('/workspace/store/messages.db')
rows = conn.execute("""
    SELECT id, timestamp, sender_name, content, is_from_me
    FROM messages
    WHERE chat_jid = ?
      AND content LIKE '%' || ? || '%'
    ORDER BY timestamp DESC
    LIMIT 20
""", (chat_jid, keyword)).fetchall()
for r in rows: print(r)
conn.close()
```

`NANOCLAW_CHAT_JID` is always set in the container env — use it. Picking a chat with `SELECT jid FROM chats LIMIT 1` returns whatever row SQLite surfaces first, which in a multi-group deployment silently queries the wrong chat. And always bind the keyword as a parameter, never interpolate it into the query string — user text may contain quotes that break the SQL or broaden the match unexpectedly.

## Database schema (quick reference)

```sql
messages(id, chat_jid, sender, sender_name, content, timestamp, is_from_me, is_bot_message)
chats(jid, name, last_message_time, channel, is_group)
```

- `is_from_me = 1` — messages from the bot (your own responses)
- `is_from_me = 0` — messages from users
- `sender` — numeric user ID (stable across name changes)
- `sender_name` — display name with username, e.g. `Leonid (@ligolnik)`, `JBáruch (@JBaruch)`
- `content` — full message text

## Connecting people to history

`sender_name` contains both the display name AND the username. When someone in the current conversation references past messages ("I told you yesterday"), match their Telegram username or name against `sender_name`:

```python
# Find what @ligolnik said yesterday
rows = conn.execute("""
    SELECT timestamp, content FROM messages
    WHERE sender_name LIKE '%ligolnik%'
      AND timestamp > datetime('now', '-2 days')
    ORDER BY timestamp DESC LIMIT 10
""").fetchall()
```

This is critical after a session nuke — you have no memory of who said what, but the database does.

## Unanswered message detection

After a session nuke or on first message in a new session, check for messages you never replied to:

```bash
python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/check-unanswered.py
```

The script outputs JSON with an `unanswered` array. A message is "answered" only if a bot message exists with `reply_to_message_id` pointing to it. No reply-thread = not an answer.

If you find unanswered messages: acknowledge the gap and respond to any that are still actionable. Don't pretend they didn't happen.

## When to use

- User references something from an earlier session that's not in active context
- User says "ты говорил..." (you said...) and you don't have it in context
- Someone says "I told you" / "we discussed" / "yesterday I asked" — match their username to DB history
- Any "I don't remember" impulse — check first
- After context compaction (the summary will mention "continued from previous session")
- First message after a nuke — check for unanswered messages from before the nuke

## Post-compaction skill blocks are HISTORY, not new tasks

When the conversation resumes after compaction, the system-reminder tail contains a block whose body opens with *"The following skills were invoked in this session. Continue to follow these guidelines:"*, then for each invocation lists a `### Skill:` header, the skill's path, and an `ARGUMENTS:` line carrying the full text of the original invocation (including any URLs or parameters).

That block is a **record of what already ran during the now-compacted window**. It is NOT a re-up of the request. The skill already executed, the tool calls already happened, the side effects (scrapes, messages, file writes) already landed. Re-executing it duplicates work and can spam the user.

**Before treating any skill in a post-compaction system-reminder as a fresh task:**

1. Read the conversation summary's **Current Work** and **Optional Next Step** sections. These reflect the actual state at compaction time. If the skill ARGUMENTS aren't mentioned there, the skill was already handled and the summary moved on.
2. Read the **most recent user message** in the summary's "All user messages" list. If the user's last move was NOT the skill invocation (e.g. they replied "понял" or moved to a different topic), the skill is closed.
3. If ambiguous, ask before re-executing anything with visible side effects (browser scraping, sending messages, writing files, GitHub API calls).

**Reference incident — 2026-04-24 / repeat 2026-04-25 (JCON-2026 speakers scrape):** A post-compaction system-reminder included an `agent-browser` invocation with JCON-2026-speakers ARGUMENTS. On both days the agent treated it as a new task and re-ran the entire scrape + report — Baruch had finished that task hours earlier ("мы закончили с этим часа 4 назад"). The actual pending work was unrelated (continuing skill patches per the summary's Optional Next Step). The repeat one day later, despite a memory entry warning against this exact failure, is what motivated #104 (kill auto-compaction).

The ARGUMENTS block is context about what the agent did. It is not a re-up of the request.

## This is a hard requirement

Claiming lost context without checking the database is a failure mode equivalent to fabrication. The information exists. Retrieve it.
