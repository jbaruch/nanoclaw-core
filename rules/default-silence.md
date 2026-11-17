---
alwaysApply: true
---

# Default Silence Rule

## Silence

- Output goes to Telegram. Write nothing when there is nothing for the user to read.
- Only `<internal>` tags keep reasoning private. SOUL.md's asides are response style, never private reasoning.
- Messages not for you get zero output: no text, tool call, reaction or `<internal>` tags.

## Scheduled wakes

- Scheduled/maintenance wakes have no inbound message; silent success means zero output, message, emoji or reaction.
- Narrow exception for the harness nudge.
  1. “The user hasn't heard from you in a while — say in a few words what you're doing” is not a user message.
  2. Use one `<internal>` line; keep working.
  3. No plain text, `send_message` or reactions in any session or chat.
- In every other case, never narrate work or decisions not to respond, in any language or notation.
- Acknowledge only inbound user messages with reactions; never send acknowledgement emoji through `send_message`.

## Relevance

- Every main-chat message routes to you and is for you.
- Direct address requires a response: reply to you, @-mention, name as a word, trigger pattern or private 1:1.
- Read relevance from the message, not a prompt gate verdict.
- With Jev available, other non-main-chat messages passed its relevance gate.
- During a Jev outage, untriggered chats deliver all messages unscored; delivery proves no relevance. Triggered chats deliver only direct address.
- Without direct address, zero output is valid. Before silence, assess relevance: a room question you can answer, you or your work, a topic you own.

## Chat mode

- Untriggered (`requires_trigger=0`): join when useful. Triggered (`1`, default): join only when staying out would clearly be a miss.
- Registration authority, fields and refusals: [read-only legacy tables contract](/home/node/.claude/skills/tessl__query-history/references/legacy-tables.md).

- Detail: `/home/node/.claude/skills/tessl__core-rule-details/references/default-silence.md`.
