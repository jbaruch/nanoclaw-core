---
name: query-history
description: Search messages.db for past chat history by keyword and/or sender username. Use when the user references past messages, after context compaction, after a session nuke, or anywhere `rules/context-recovery.md` requires checking the message history before claiming lost context.
---

# Query Message History Skill

Process steps in order. Do not skip ahead.

## Step 1 — Run the query

Run the helper with at least one filter set:

```bash
python3 /home/node/.claude/skills/tessl__query-history/scripts/query-message-history.py --keyword "<text>"
```

Provide at least one of `--keyword <text>` (matches `content`) or `--sender <name>` (matches `sender_name`); both can be combined and AND together. `--limit N` defaults to 20 and is capped at 50 rows per `rules/query-size-limits.md` — the script rejects higher values at exit 2. Chat scope comes from the `NANOCLAW_CHAT_JID` env var, set automatically inside every container; no chat selection happens at the call site. The script wraps `LIKE` matches with explicit escape, so user-supplied `%` / `_` / `\` characters match literally. The DB is opened read-only via `file:…?mode=ro`, so a missing or mistyped `NANOCLAW_DB` fails at connect time rather than silently creating a bogus empty database. Proceed immediately to Step 2.

## Step 2 — Read the JSON output and act on it

The script prints a single-line JSON payload to stdout: `{rows, chat_jid, query, error}`. Each entry in `rows` carries `id`, `timestamp`, `sender_name`, `content`, `is_from_me`. Newest-first ordering. `error` is `null` on clean success and a short string on failure (DB unreadable, missing env var); the script also exits non-zero on those failure paths (1 = runtime, 2 = usage). If `rows` is empty AND `error` is `null`, the search ran cleanly with no matches — proceed silently with that information; do not fabricate matches. If `error` is non-null, surface the error to the caller and stop. Otherwise return the matched rows in the format the caller needs. Finish here.
