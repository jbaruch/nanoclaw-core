---
alwaysApply: true
---

# Telegram Communication Protocol

## Required Read

- Before Telegram reactions or messages, read `skills/core-behavior/references/telegram-protocol.md` in full, including before relying on a threading carve-out.
- Resolve references within the installed `jbaruch/nanoclaw-core` plugin.
- Reference directives are binding; read explicitly, never through an `@` import.
- If a reference is missing or unreadable, stop the affected action until repaired.

## Acknowledgement

- Runtime 👀 acknowledges addressed messages; do not duplicate it.
- Upgrade reactions only after inspecting the message, under the reference's Acknowledgement contract.
- Jev-passed unaddressed messages get no runtime reaction; follow `rules/core-behavior.md` Async Tasks when answering a long task, and add none when silent.
- React, work, deliver; never send an "I'm starting now" reply.

## Threading

- Pass `reply_to` from the inbound `<message id="...">` tag when answering a user message.
- Narrow exception for the reference's Reply threading carve-outs.
- Applies to `pin: true`, `sender` set, or maintenance / scheduled-task sessions.
- Preconditions are binding: read `skills/core-behavior/references/telegram-protocol.md` Reply threading before relying on it.
- Every other answer to a user message requires `reply_to`.

## Formatting

- Use Telegram HTML and `•` bullets.
- Follow the reference's Formatting contract for supported tags and hook rewrites.
- Escape only `<`, `>` and `&` in user data; never escape apostrophes or double quotes as `&apos;` / `&quot;`.
