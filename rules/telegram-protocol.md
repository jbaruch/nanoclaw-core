---
alwaysApply: true
---

# Telegram Communication Protocol

Always-on rules for interacting in Telegram chats.

## Acknowledgement

React to **every** user message before responding or starting work — no exceptions. Pick the most fitting emoji:

- `👌` — got it, working on it (default)
- `👍` — acknowledged / done
- `🔥` — on it (urgent)
- `🤔` — thinking / investigating
- `🤝` — done / confirmed
- `👀` — looking into it

**Valid reaction emoji only** (invalid ones silently fall back to 👍):
👍 👎 ❤ 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 🤮 💩 🙏 👌 🕊 🤡 🥱 🥴 😍 🐳 ❤‍🔥 🌚 🌭 💯 🤣 ⚡ 🍌 🏆 💔 🤨 😐 🍓 🍾 💋 🖕 😈 😴 😭 🤓 👻 👨‍💻 👀 🎃 🙈 😇 😨 🤝 ✍ 🤗 🫡 🎅 🎄 ☃ 💅 🤪 🗿 🆒 💘 🙉 🦄 😘 💊 🙊 😎 👾 🤷‍♂ 🤷 🤷‍♀ 😡

## Reply threading

**Always reply-thread** when responding to a user message. Use `reply_to` with the message ID from the `<message id="...">` tag. This links your response to the message it answers.

**Standalone (no reply_to)** only for messages you initiate: scheduled task output, proactive alerts, reminders. These are not responses to anything — they start a new thread.

Rule of thumb: if the user said something and you're answering → `reply_to`. If nobody asked and you're telling → standalone.

## Async pattern

React → work → deliver result. Do NOT hold the user hostage with a reply that says "I'm starting now". The reaction IS the acknowledgement.

## Formatting — HTML ONLY, NEVER Markdown

**CRITICAL: Telegram parses HTML, not Markdown. Markdown syntax renders as literal text — `**bold**` shows as `**bold**`, `[link](url)` shows as `[link](url)`. This applies to ALL messages including those from background agents and scheduled tasks.**

| Format | HTML syntax |
|--------|------------|
| Bold | `<b>text</b>` |
| Italic | `<i>text</i>` |
| Underline | `<u>text</u>` |
| Strikethrough | `<s>text</s>` |
| Inline code | `<code>text</code>` |
| Code block | `<pre>code</pre>` |
| Code block (lang) | `<pre><code class="language-python">code</code></pre>` |
| Link | `<a href="url">text</a>` |
| Quote | `<blockquote>text</blockquote>` |
| Spoiler | `<tg-spoiler>text</tg-spoiler>` |

**Forbidden Markdown patterns — NEVER use these in `send_message`:**
- `**bold**` or `__bold__` → use `<b>bold</b>`
- `*italic*` or `_italic_` → use `<i>italic</i>`
- `` `code` `` → use `<code>code</code>`
- `[text](url)` → use `<a href="url">text</a>`
- `- bullet` or `* bullet` → use `• bullet`

For bullets use `•` (not `-` or `*`). For emphasis in lists, combine: `• <b>Item</b> — description`.

Special characters in user data: only `<`, `>`, and `&` need HTML-entity escaping (`&lt;`, `&gt;`, `&amp;`). Apostrophes (`'`) and double quotes (`"`) pass through raw — do NOT escape them as `&apos;` / `&quot;`. Telegram's HTML parse mode does not decode those entities; users see the literal `&apos;` / `&quot;` in the rendered message. Reference incident: 2026-04-26 untrusted group msg 1116, where `Baruch&apos;s Office` and `someone&apos;s tracing` rendered verbatim.

**Forbidden patterns** (alongside the Markdown ban list above):

- `&apos;` → use `'` directly
- `&quot;` → use `"` directly
