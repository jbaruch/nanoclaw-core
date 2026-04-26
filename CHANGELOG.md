# Changelog

## Unreleased

### Rules

- **no-lazy-verification** — New core rule. If a tool exists that can verify an external claim, the agent MUST use it before reporting "can't verify" or punting on the check. Lists the priority order — JS-capable browser → domain API → static fetch → code execution — and bans the common stop-conditions ("site is JS-rendered", "page is thin/empty", "I can't access this") that collapse the moment a real browser or API call is tried. Reference incident: dev2next CFP verification, 2026-04-22 — agent dismissed a live-browser option with "сайт почти пустой, JS-рендер" when a JS-capable browser tool was available and would have returned the deadline in one call.
- **context-recovery** — Adds a "Post-compaction skill blocks are HISTORY, not new tasks" section. The system-reminder block listing skills invoked during the now-compacted window is a record, not a re-up of the request — re-executing it duplicates work and can spam the user. Reference incident: 2026-04-24 / 2026-04-25 JCON-2026 speakers scrape repeated twice across consecutive sessions despite a memory entry warning against this exact failure mode (motivated #104).

### Surface sync

- `tile.json` adds `entrypoint: README.md` and a `rules` entry for `no-lazy-verification`.
- `README.md` and `CHANGELOG.md` introduced (none existed previously). Both will be maintained going forward as required by `jbaruch/coding-policy: context-artifacts`.
