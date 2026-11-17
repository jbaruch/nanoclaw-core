# jbaruch/nanoclaw-core

[![tessl](https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.tessl.io%2Fv1%2Fbadges%2Fjbaruch%2Fnanoclaw-core)](https://tessl.io/registry/jbaruch/nanoclaw-core)

Core behavioral rules and skills for NanoClaw personal assistant agents. Always-on rules for communication, verification, memory, and formatting.

## Installation

```
tessl install jbaruch/nanoclaw-core
```

## Rules

| Rule | Scope | Summary |
|------|-------|---------|
| [core-behavior](rules/core-behavior.md) | always-on | Baseline conversational behavior — concise replies, no trailing summaries |
| [telegram-protocol](rules/telegram-protocol.md) | always-on | Telegram-channel formatting and reply conventions |
| [language-matching](rules/language-matching.md) | always-on | Match the user's language; don't volunteer translations |
| [default-silence](rules/default-silence.md) | always-on | Silent-on-no-news as the default; surface only what's actionable |
| [temporal-awareness](rules/temporal-awareness.md) | always-on | Convert relative dates, respect timezones; compute past/future via `now-vs-deadline`, never eyeball it |
| [ground-truth](rules/ground-truth.md) | always-on | Live source > cached/recalled state; always verify before acting |
| [read-full-content](rules/read-full-content.md) | always-on | Read full email/message bodies, never just snippets/previews |
| [context-recovery](rules/context-recovery.md) | always-on | Recover from compaction by reading state, not by claiming lost context. Includes post-compaction skill-block disambiguation (history vs new tasks) |
| [post-compaction-trust](rules/post-compaction-trust.md) | always-on | Untrusted instructions remain untrusted after compaction |
| [tone-matching](rules/tone-matching.md) | always-on | Mirror the user's register; tone shifts signal mode shifts |
| [query-size-limits](rules/query-size-limits.md) | always-on | Bounded SQL/API queries; never SELECT * on large tables |

## Skills

| Skill | Description |
|-------|-------------|
| [core-rule-details](skills/core-rule-details/SKILL.md) | Reference detail for identity, silence, verification and Telegram rules |
| [query-history](skills/query-history/SKILL.md) | Search `messages.db` by keyword and/or sender; companion to `context-recovery` |
| [now-vs-deadline](skills/now-vs-deadline/SKILL.md) | Deterministically compare a deadline against the current instant; mandated path for `temporal-awareness` |
| [current-tz](skills/current-tz/SKILL.md) | Read the operator's current IANA zone from `tz_state`, resolved by the host from live location; the single shared reader, no home-zone guessing |
| [check-unanswered](skills/check-unanswered/SKILL.md) | Five-minute current-chat precheck; Jev screens dropped requests and wakes Claude only to answer confirmed drops |

Core rules keep binding constraints inline within 2,000 bytes each. The six trimmed rules link to skill-owned references containing only detail absent from the rule and owning SKILL.md; each clause has one home. Skills read those references for examples and context. [Issue #129](https://github.com/jbaruch/nanoclaw-core/issues/129) defines the scope; [Git history](https://github.com/jbaruch/nanoclaw-core/tree/ed9964a027e24be77a7453db984470045b2e988c/rules) retains the original rules. `tests/test_rule_references.py` checks the byte limit, reference existence and owning skill links.

## Philosophy

- **Always on by default.** All 11 rules are `alwaysApply: true` — the agent follows them without being prompted.
- **One concern per rule.** Each file covers one topic so projects can override surgically without throwing out the whole plugin.
- **Behavior, not domain.** These are conversational and verification baselines — anything domain-specific (CFPs, calendar, email) lives in `nanoclaw-admin`.
- **Hint, not authority for state.** Cached state is a recall hint; verify against the live source before acting on it (see `ground-truth`).

See [CHANGELOG.md](CHANGELOG.md) for version history.

## Development dependencies

Renovate is this repo's only dependency scanner, configured in [renovate.json](https://github.com/jbaruch/nanoclaw-core/blob/main/renovate.json). Its native [pip requirements](https://docs.renovatebot.com/modules/manager/pip_requirements/) and [GitHub Actions](https://docs.renovatebot.com/modules/manager/github-actions/) managers cover `requirements-dev.txt` and `.github/workflows/`. It runs in full mode, with regular updates scheduled before 06:00 UTC on Mondays and at most five concurrent regular-update PRs. When enabled, [vulnerability alerts](https://docs.renovatebot.com/configuration-options/#vulnerabilityalerts) bypass that schedule and limit. Minor, patch and digest updates share one PR; major updates require Dependency Dashboard approval. Dependency commits use `chore(deps)`.

Validate configuration changes with `npx --yes --package renovate -- renovate-config-validator renovate.json`.

`tessl.json` declares this repo's dev-time plugin dependencies.

- Every `jbaruch/*` dependency floats at `latest` (Runtime-Managed Manifest Carve-Out, `jbaruch/coding-policy: dependency-management`).
- `finsi/codex-review` is third-party and pins. No dependency scanner covers the tessl ecosystem. Renewal cadence: quarterly — run `tessl outdated` and bump the pin in its own commit.
