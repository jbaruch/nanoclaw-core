---
name: check-unanswered
description: Finds user messages that never got a threaded bot reply. A message is "answered" only if a bot message exists with reply_to_message_id pointing to it. Deterministic script. Use when checking for missed messages, unresponded messages, dropped replies, or messages without responses — such as during context recovery or heartbeat checks.
---

# Check Unanswered Messages

```bash
python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/check-unanswered.py
```

Outputs JSON with `unanswered` array. Empty = nothing to report.

A bot message "answers" a user message only when `reply_to_message_id = user_msg.id`. Standalone bot messages are not answers.

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
