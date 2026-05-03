---
alwaysApply: true
---

# Context Recovery — Never Lose History

## The Rule

**Never say you've lost context or forgotten a previous conversation without querying `messages.db` for it.**

This rule is **conditional** — it fires only when the agent is about to claim lost context. It is not the per-message first action (the runtime react hook is); it operates as a gate on a specific class of replies.

The full message history is always available at `/workspace/store/messages.db`. Context compaction removes it from your active context — but the database still has it. There is no excuse for "I don't remember what we discussed" when the database is a query away.

## Required behavior

Before responding with any variant of:
- "Потерял контекст"
- "I don't remember this thread"
- "What were we discussing?"
- "I don't have context on this topic"
- Any acknowledgment that prior conversation is unavailable

You **MUST** run `skills/query-history/scripts/query-message-history.py` — the messages.db search helper from this tile's `query-history` skill — with at least `--keyword "<text>"`:

```bash
python3 skills/query-history/scripts/query-message-history.py --keyword "<text>"
```

Filters: `--sender <name>` (matches `sender_name`, see "Connecting people to history" below), `--limit N` (default 20, capped at 50 per `rules/query-size-limits.md`). Output is single-line JSON on stdout; chat scope comes from `NANOCLAW_CHAT_JID`.

(Runtime note: inside agent containers the script is installed at `/home/node/.claude/skills/tessl__query-history/scripts/query-message-history.py` per the standard `skills/<name>` → `tessl__<name>` mount convention documented in `.github/copilot-instructions.md`.)

## Database schema (quick reference)

```sql
messages(id, chat_jid, sender, sender_name, content, timestamp, is_from_me, is_bot_message)
chats(jid, name, last_message_time, channel, is_group)
```

- `is_from_me = 1` — messages from the bot (your own responses)
- `is_from_me = 0` — messages from users
- `sender` — numeric user ID (stable across name changes)
- `sender_name` — display name with username, e.g. `Alice (@alice)`, `Bob (@bob)`
- `content` — full message text

## Connecting people to history

`sender_name` is `Display (@username)`, so a username fragment matches via `--sender` (same script, `skills/query-history/scripts/query-message-history.py`):

```bash
python3 skills/query-history/scripts/query-message-history.py --sender ligolnik
```

Combine with `--keyword` to narrow with AND. Critical after a session nuke — you have no memory of who said what, but the database does.

## When to use

- User references something from an earlier session that's not in active context
- User says "ты говорил..." (you said...) and you don't have it in context
- Someone says "I told you" / "we discussed" / "yesterday I asked" — match their username to DB history
- Any "I don't remember" impulse — check first
- After context compaction (the summary will mention "continued from previous session")

## Post-compaction skill blocks are HISTORY, not new tasks

When the conversation resumes after compaction, the system-reminder tail contains a block whose body opens with *"The following skills were invoked in this session. Continue to follow these guidelines:"*, then for each invocation lists a `### Skill:` header, the skill's path, and an `ARGUMENTS:` line carrying the full text of the original invocation (including any URLs or parameters).

That block is a **record of what already ran during the now-compacted window**. It is NOT a re-up of the request. The skill already executed, the tool calls already happened, the side effects (scrapes, messages, file writes) already landed. Re-executing it duplicates work and can spam the user.

**Before treating any skill in a post-compaction system-reminder as a fresh task:**

1. Read the conversation summary's **Current Work** and **Optional Next Step** sections. These reflect the actual state at compaction time. If the skill ARGUMENTS aren't mentioned there, the skill was already handled and the summary moved on.
2. Read the **most recent user message** in the summary's "All user messages" list. If the user's last move was NOT the skill invocation (e.g. they replied "понял" or moved to a different topic), the skill is closed.
3. If ambiguous, ask before re-executing anything with visible side effects (browser scraping, sending messages, writing files, GitHub API calls).

**Reference incident — 2026-04-24 / repeat 2026-04-25 (JCON-2026 speakers scrape):** A post-compaction system-reminder included an `agent-browser` invocation with JCON-2026-speakers ARGUMENTS. On both days the agent treated it as a new task and re-ran the entire scrape + report — the owner had finished that task hours earlier ("мы закончили с этим часа 4 назад"). The actual pending work was unrelated (continuing skill patches per the summary's Optional Next Step). The repeat one day later, despite a memory entry warning against this exact failure, is what motivated #104 (kill auto-compaction).

The ARGUMENTS block is context about what the agent did. It is not a re-up of the request.

## This is a hard requirement

Claiming lost context without checking the database is a failure mode equivalent to fabrication. The information exists. Retrieve it.
