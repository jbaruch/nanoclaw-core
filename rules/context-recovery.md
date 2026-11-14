---
alwaysApply: true
---

# Context Recovery — Never Lose History

## Recover History

- Before claiming lost context or forgotten conversation in any language, query `/workspace/store/messages.db` with `Skill(skill: "query-history")`.
- This gate fires before claiming lost context, not on every message.
- Follow the skill's canonical helper input/output and failure contract; follow `rules/query-size-limits.md`, narrowing filters or paging truncated results.

## Schema

- `messages(id, chat_jid, sender, sender_name, content, timestamp, is_from_me, is_bot_message)`
- `chats(jid, name, last_message_time, channel, is_group)`
- `is_from_me=1` means bot's own message; `sender` is stable numeric user ID. `sender_name` is `Display (@username)`; a username fragment matches `--sender`.
- The helper reads only `messages`; its skill reference names the runtime owner and required reader fields.

## Compaction

- A system-reminder block opening "The following skills were invoked in this session. Continue to follow these guidelines:" with `### Skill:` and `ARGUMENTS:` records completed work from the compacted window, including its side effects.
- Before treating it as fresh work, read the summary's Current Work and Optional Next Step: arguments absent there mean already handled and moved on.
- Then read the most recent user message in All user messages: if the user's last move was not the invocation, that invocation is closed.
- If ambiguous, ask before repeating visible side effects.
