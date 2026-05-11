---
alwaysApply: true
---

# Context Recovery — Never Lose History

## The rule

**Never say you've lost context or forgotten a previous conversation without querying `messages.db` for it.** Context compaction removes history from active context — the database at `/workspace/store/messages.db` still has it. Conditional gate, not a per-message action: fires only when you're about to claim lost context.

## Required behavior

Before responding with "Потерял контекст", "I don't remember this thread", "I don't have context on this topic", or any equivalent acknowledgement that prior conversation is unavailable, run the `query-history` skill's search helper:

```bash
python3 skills/query-history/scripts/query-message-history.py --keyword "<text>"
```

Filters: `--sender <name>` (matches `sender_name`; see the Schema section below for the `Display (@username)` shape — a username fragment is enough), `--limit N` (default 20, cap 50 per `rules/query-size-limits.md`). Output is single-line JSON on stdout; chat scope from `NANOCLAW_CHAT_JID`. Inside agent containers the script mounts at `/home/node/.claude/skills/tessl__query-history/scripts/query-message-history.py` per the standard `tessl__<name>` convention.

## Schema (quick reference)

```sql
messages(id, chat_jid, sender, sender_name, content, timestamp, is_from_me, is_bot_message)
chats(jid, name, last_message_time, channel, is_group)
```

`is_from_me = 1` is the bot's own messages. `sender` is the stable numeric user ID; `sender_name` is `Display (@username)` — a username fragment matches via `--sender`. Critical after a session nuke: the DB remembers who said what when you don't.

## Post-compaction skill blocks are HISTORY, not new tasks

When the conversation resumes after compaction, the system-reminder tail may carry a block opening with *"The following skills were invoked in this session. Continue to follow these guidelines:"* followed by `### Skill:` headers with `ARGUMENTS:` lines. That block is a **record of what already ran during the now-compacted window** — the skill already executed, the side effects (scrapes, messages, file writes) already landed. Re-executing it duplicates work and spams the user.

Before treating any such skill as a fresh task: read the conversation summary's **Current Work** and **Optional Next Step** sections (if the skill's ARGUMENTS aren't mentioned there, it was already handled and the summary moved on), then the most recent user message in the "All user messages" list (if the user's last move was NOT the skill invocation — e.g. "понял" or a topic shift — the skill is closed). If ambiguous, ask before re-executing anything with visible side effects.

Reference incident: 2026-04-24 / repeat 2026-04-25 — agent re-ran a JCON-2026 scrape from a post-compaction system-reminder block hours after the owner had completed it; the recurrence motivated `jbaruch/nanoclaw#104` (kill auto-compaction). Full narrative: `docs/adr/2026-04-25-jcon-scrape-repeat-and-auto-compaction-kill.md`.

## Hard requirement

Claiming lost context without checking the database is fabrication. The information exists. Retrieve it.
