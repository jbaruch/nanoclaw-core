---
alwaysApply: true
---

# Telegram Communication Protocol

## Acknowledgement

The runtime reacts on first touch (👀) via the `react-first` UserPromptSubmit hook in the agent-runner (see `jbaruch/nanoclaw#136`) — you do NOT need to call `react_to_message` to acknowledge receipt. Use it only to upgrade with a more specific reaction *after* inspecting the message: `👌` (got it, working), `👍` (acknowledged/done), `🔥` (urgent), `🤔` (thinking/investigating), `🤝` (done/confirmed). Each `react_to_message` call replaces the prior emoji; a later, more specific one supersedes the runtime's 👀. Telegram allows only its fixed reaction-emoji set and silently falls back to 👍 for any unsupported emoji, so the five above are safe and any other guess is harmless.

## Reply threading

The `reply-threading-enforcement` PreToolUse hook (`jbaruch/nanoclaw#137`) denies a standalone `send_message` while the latest user inbound is unanswered — threading is a runtime contract, not a convention. Pass `reply_to` with the message ID from the `<message id="...">` tag for any response to a user message. Carve-outs that bypass the gate: `pin: true` (status updates / daily briefings), `sender` set (multi-bot persona), maintenance / scheduled-task session. Rule of thumb: user said something and you're answering → `reply_to`; nobody asked and you're telling → standalone (e.g. scheduled-task output).

## Async pattern

React → work → deliver result. The reaction (auto-emitted by the runtime) IS the acknowledgement — never hold the user hostage with a "I'm starting now" reply.

## Formatting

Telegram parses HTML (its own subset, including `<tg-spoiler>`), not Markdown. The `no-markdown-in-send-message` PreToolUse hook (`jbaruch/nanoclaw#138`) auto-rewrites the four common Markdown leaks (`**bold**` → `<b>`, `[label](url)` → `<a href>`, `` `code` `` → `<code>`, `- ` / `* ` line bullets → `•`), so emit raw HTML only for the formats the hook doesn't cover: `<i>`, `<u>`, `<s>`, `<pre>` (optional `<code class="language-python">` for syntax highlighting — substitute the actual language, not a placeholder), `<blockquote>`, `<tg-spoiler>`. For bullets use `•`.

Special-character escaping in user data: only `<`, `>`, `&` need HTML entities (`&lt;`, `&gt;`, `&amp;`). Apostrophes and double quotes pass through raw — do NOT escape them as `&apos;` / `&quot;`; Telegram's HTML parse mode doesn't decode those, so users see the literal entity text in the rendered message. Reference incident: 2026-04-26 untrusted group msg 1116 where `Owner&apos;s Office` and `someone&apos;s tracing` rendered verbatim.
