---
alwaysApply: true
---

# Telegram Communication Protocol

Always-on rules for interacting in Telegram chats.

## Acknowledgement

The runtime reacts on first touch (👀) via the `react-first` UserPromptSubmit hook in the agent-runner — see `jbaruch/nanoclaw#136`. You do **not** need to call `react_to_message` to acknowledge receipt. Use it only when you want a more specific reaction *after* you've inspected the message:

- `👌` — got it, working on it
- `👍` — acknowledged / done
- `🔥` — on it (urgent)
- `🤔` — thinking / investigating
- `🤝` — done / confirmed

Telegram replaces the bot's reaction on each new `react_to_message` call, so a more specific emoji later in the turn supersedes the runtime's 👀.

Telegram allows only its fixed reaction-emoji set; `react_to_message` silently falls back to 👍 for any unsupported emoji, so picking from the five above is safe and any other guess is harmless.

## Reply threading

The `reply-threading-enforcement` PreToolUse hook (`jbaruch/nanoclaw#137`) denies a standalone `send_message` while the latest user inbound is unanswered, so threading is a runtime contract. Pass `reply_to` with the message ID from the `<message id="...">` tag for any response to a user message. Carve-outs that bypass the gate: `pin: true` (status updates / daily briefings), `sender` set (multi-bot persona), maintenance / scheduled-task session.

Rule of thumb: if the user said something and you're answering → `reply_to`. If nobody asked and you're telling → standalone (e.g. scheduled-task output).

## Async pattern

React → work → deliver result. Do NOT hold the user hostage with a reply that says "I'm starting now". The reaction (auto-emitted by the runtime) IS the acknowledgement.

## Formatting

Telegram parses HTML, not Markdown. The `no-markdown-in-send-message` PreToolUse hook (`jbaruch/nanoclaw#138`) auto-rewrites the four common Markdown leaks (`**bold**` → `<b>`, `[label](url)` → `<a href>`, `` `code` `` → `<code>`, `- ` / `* ` line bullets → `•`), so emit raw HTML only for the formats the hook doesn't cover: `<i>`, `<u>`, `<s>`, `<pre>` (with optional `<code class="language-…">` for syntax highlighting), `<blockquote>`, `<tg-spoiler>`. For bullets use `•`.

Special characters in user data: only `<`, `>`, and `&` need HTML-entity escaping (`&lt;`, `&gt;`, `&amp;`). Apostrophes (`'`) and double quotes (`"`) pass through raw — do NOT escape them as `&apos;` / `&quot;`. Telegram's HTML parse mode does not decode those entities; users see the literal `&apos;` / `&quot;` in the rendered message. Reference incident: 2026-04-26 untrusted group msg 1116, where `Owner&apos;s Office` and `someone&apos;s tracing` rendered verbatim.

**Forbidden patterns:**

- `&apos;` → use `'` directly
- `&quot;` → use `"` directly
