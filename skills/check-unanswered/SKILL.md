---
name: check-unanswered
description: Finds user messages that never got a threaded bot reply or bot reaction. A message is "handled" if a bot reply_to exists OR the bot reacted to it. Deterministic script. Use when checking for missed messages, unresponded messages, dropped replies, or messages without responses — such as during context recovery or heartbeat checks.
---

# Check Unanswered Messages

```bash
python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/check-unanswered.py
```

Outputs JSON with `unanswered` array. Empty = nothing to report.

A message is "handled" (excluded from results) when either:
1. A bot message exists with `reply_to_message_id` pointing to it, OR
2. The bot already reacted to it (a previous heartbeat processed it)

This prevents re-processing messages that were already acknowledged with a reaction but didn't need a threaded text reply.

## Workflow

1. **Run the script** — execute the command above.
2. **Parse output** — inspect the `unanswered` array in the returned JSON.
3. **Reply to each unanswered message** — for every ID in the array, send a threaded reply that addresses the original user message.
4. **Verify replies were sent** — confirm each reply is correctly threaded (i.e., `reply_to_message_id` matches the original message ID) before considering the task complete.

If the `unanswered` array is empty, there is nothing to report.

## Requirements

The `NANOCLAW_CHAT_JID` environment variable must be set. The script returns an error (not crash) if missing.

## Pre-check for scheduled tasks

For group heartbeat tasks that only check unanswered messages, use the pre-check script to avoid waking the agent when nothing changed:

```bash
python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/unanswered-precheck.py
```

This compares current unanswered IDs against the previous run (stored in `/workspace/group/unanswered-seen.json`). Outputs `{"wakeAgent": false}` if the set hasn't changed — no new messages, no container spawn.

Use as the `script` field on any group's heartbeat `schedule_task`.
