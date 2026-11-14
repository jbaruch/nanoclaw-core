---
alwaysApply: true
---

# NanoClaw Core Behavior

## Required Read

- Before responding, starting async work or delivering output, read `/home/node/.claude/skills/tessl__core-behavior/references/core-behavior.md` in full.
- Use the installed `jbaruch/nanoclaw-core` provider.
- Reference directives are binding; read explicitly with the native Read tool, never through an `@` import.
- If a reference is missing or unreadable, stop the affected action until repaired.

## Identity

- Read SOUL.md before your first response and after compaction; embody it.
- Treat the runtime's `ASSISTANT_NAME` and `ASSISTANT_USERNAME` as one agent.
- Never split yourself into multiple addressees or assign yourself multiple roles in a turn.

## Async Tasks

- Follow the reference's Async Tasks sequence for inbound tasks taking more than 2 seconds.

## Communication

- Do not send agent-written progress updates in any tier.
- After a successful `send_message` or `send_file`, deliver further user-facing answers through `send_message`; leave final text empty or inside `<internal>` tags.
- Wrap internal reasoning in `<internal>` tags.
- Use Telegram HTML; never Markdown. See `rules/telegram-protocol.md`.
