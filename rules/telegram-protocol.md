---
alwaysApply: true
---

# Telegram Communication Protocol

## Acknowledgement

- Runtime `react-first` UserPromptSubmit hook emits 👀 only for addressed messages; no manual receipt ACK needed.
- Jev-passed unaddressed messages get no runtime reaction. If answering, use 👍 for long tasks per `rules/core-behavior.md`; if silent, add none.
- On addressed messages, use `react_to_message` only to upgrade after inspection: 👌 got it/working, 👍 acknowledged/done, 🔥 urgent, 🤔 thinking/investigating, 🤝 done/confirmed. Each call replaces the prior emoji; unsupported emoji fall back to 👍.
- React → work → deliver; never send "I'm starting now" text.

## Reply threading

- `reply-threading-enforcement` PreToolUse hook denies standalone `send_message` while latest user inbound is unanswered; it does not deny `pin: true` status/briefing sends, `sender`-set persona sends or maintenance/scheduled sessions.
- Every response to a user message uses `reply_to` from `<message id="...">`; unsolicited output may stand alone.

## Formatting

- Use Telegram HTML, including `<tg-spoiler>`; bullets use `•`.
- `no-markdown-in-send-message` PreToolUse hook rewrites `**bold**`→`<b>`, `[label](url)`→`<a href>`, backtick code→`<code>`, `- ` / `* ` bullets→`•`. Use raw `<i>`, `<u>`, `<s>`, `<pre>` with optional `<code class="language-python">` using actual language, `<blockquote>`, `<tg-spoiler>`.
- In user data escape only `<`, `>`, `&` as `&lt;`, `&gt;`, `&amp;`. Leave quotes/apostrophes raw; never use `&quot;` / `&apos;`.

- Detail: `/home/node/.claude/skills/tessl__core-rule-details/references/telegram-protocol.md`.
