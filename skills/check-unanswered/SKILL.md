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
