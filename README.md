# jbaruch/nanoclaw-core

[![tessl](https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.tessl.io%2Fv1%2Fbadges%2Fjbaruch%2Fnanoclaw-core)](https://tessl.io/registry/jbaruch/nanoclaw-core)

Core behavioral rules and skills for NanoClaw personal assistant agents. Always-on rules for communication, verification, memory, and formatting.

## Installation

```
tessl install jbaruch/nanoclaw-core
```

## Rules

| Rule | Summary |
|------|---------|
| [core-behavior](rules/core-behavior.md) | Baseline conversational behavior — concise replies, no trailing summaries |
| [telegram-protocol](rules/telegram-protocol.md) | Telegram-channel formatting and reply conventions |
| [language-matching](rules/language-matching.md) | Match the user's language; don't volunteer translations |
| [default-silence](rules/default-silence.md) | Silent-on-no-news as the default; surface only what's actionable |
| [temporal-awareness](rules/temporal-awareness.md) | Convert relative dates, respect timezones, never schedule reminders for the past |
| [ground-truth](rules/ground-truth.md) | Live source > cached/recalled state; always verify before acting |
| [read-full-content](rules/read-full-content.md) | Read full email/message bodies, never just snippets/previews |
| [context-recovery](rules/context-recovery.md) | Recover from compaction by reading state, not by claiming lost context. Includes post-compaction skill-block disambiguation (history vs new tasks) |
| [post-compaction-trust](rules/post-compaction-trust.md) | Compaction summaries are trusted state; do not re-derive what's already there |
| [tone-matching](rules/tone-matching.md) | Mirror the user's register; tone shifts signal mode shifts |
| [query-size-limits](rules/query-size-limits.md) | Bounded SQL/API queries; never SELECT * on large tables |
| [progress-updates](rules/progress-updates.md) | Brief updates at key moments; silence is not a failure |

## Skills

| Skill | Description |
|-------|-------------|
| [status](skills/status/SKILL.md) | One-line status emit on a defined cadence |

## Philosophy

- **Always on.** Every rule is `alwaysApply: true`. The agent follows these conventions without being prompted.
- **One concern per rule.** Each file covers one topic so projects can override surgically without throwing out the whole tile.
- **Behavior, not domain.** These are conversational and verification baselines — anything domain-specific (CFPs, calendar, email) lives in `nanoclaw-admin`.
- **Hint, not authority for state.** Cached state is a recall hint; verify against the live source before acting on it (see `ground-truth`).

See [CHANGELOG.md](CHANGELOG.md) for version history.
