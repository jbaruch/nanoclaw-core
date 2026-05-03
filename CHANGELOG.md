# Changelog

## Unreleased

### Skills — added

- **`query-history` (new)** (`jbaruch/nanoclaw-admin#181`, umbrella `jbaruch/nanoclaw-admin#180` RULES.md diet) — A minimal companion skill for the `context-recovery` rule. Hosts `scripts/query-message-history.py` — a CLI helper with `--keyword`, `--sender`, `--limit` flags, JSON-on-stdout output, and 13 tests. Replaces the inlined Python snippets that lived in `rules/context-recovery.md`. The script enforces three correctness contracts the inlined snippets did not: (a) `escape_like` + `LIKE … ESCAPE '\\'` so user-supplied `%` / `_` / `\` characters match literally instead of acting as wildcards; (b) `--limit` capped at 50 rows per `rules/query-size-limits.md` (rejected at exit 2 with a pointer to that rule); (c) read-only DB open via `file:…?mode=ro` URI so a missing/mistyped `NANOCLAW_DB` fails fast instead of silently creating an empty SQLite file. `tessl skill review skills/query-history` reports 86% (threshold 85). Originally proposed against `skills/check-unanswered/scripts/` in PR #40 v1; that skill was retired in `nanoclaw-core#39` while this PR was open — query-history is the new home and the rule reference (`/home/node/.claude/skills/tessl__query-history/scripts/query-message-history.py`) follows.

### Skills — removed

- **`check-unanswered` — deleted** (`jbaruch/nanoclaw-core#38`). The skill ran as Step 1 of every heartbeat (every 30 min, every group with `enableHeartbeat`). In practice it almost always either found nothing or surfaced a candidate the bot had already answered inline → reacts 👍. Genuinely-dropped messages — the failure mode the skill existed to catch — turned out rare enough that the steady-state token cost (LLM reasoning over `surrounding_context` for every candidate, every 30 min, every active group) wasn't justified. Removes `skills/check-unanswered/` (SKILL.md + `check-unanswered.py` + `unanswered-precheck.py`) and the matching `tests/test_check_unanswered.py` / `tests/test_unanswered_precheck.py` plus the `check_unanswered` and `unanswered_precheck` `conftest.py` fixtures. `tile.json` and `README.md` skills tables drop the entry; `.github/copilot-instructions.md` and `rules/context-recovery.md` lose the references to the script and its env var. **Supersedes the still-unreleased `unanswered-precheck.py backfill` and `pytest baseline + CI gate` Test-infrastructure entries below — those described coverage for the now-deleted scripts; with the scripts gone the test scaffolding for them goes too. The pytest scaffold itself (pyproject + workflow + dev requirements) survives and continues to cover the remaining `container-uptime` script and any new ones.** The orchestrator-side cleanup (heartbeat-precheck.py block, heartbeat SKILL.md Step 3, `system-audit.py` known-non-skill list, `manage-groups` Step 3 `enableHeartbeat` blurb, plus the placement / writing-guide rule examples) ships as the matching `jbaruch/nanoclaw-admin` PR; the trusted-tile heartbeat-flow doc cleanup ships as the matching `jbaruch/nanoclaw-trusted` PR.

### Rules

- **`context-recovery.md` — extract messages.db Python snippet to `query-history` skill** (`jbaruch/nanoclaw-admin#181`, umbrella `jbaruch/nanoclaw-admin#180` RULES.md diet) — The rule inlined two Python snippets (a content-search query and a sender-search query) plus a paragraph reminding the reader to bind parameters and never `SELECT jid FROM chats LIMIT 1`. Snippets and the parameter-binding warning move to `skills/query-history/scripts/query-message-history.py` (see Skills — added entry above). The rule's runtime gate ("never claim lost context without querying messages.db") and the schema quick-reference stay; only the inlined snippets move. Measured against current main (post-`#39`): rule drops 5,841 → 4,946 bytes (-895).

- **`core-behavior.md` — strip deploy-specific examples from the dual-handle section** (`jbaruch/nanoclaw-core#36`). The "Trigger word and Telegram username refer to the same bot" subsection used one specific deployment's bot pair as its only example and embedded an entire reference-incident block (group name, two live message IDs, a quoted message in another language) — both inappropriate for a deploy-anywhere universal tile. Replaced with abstract prose that cites the runtime identity preamble (`ASSISTANT_NAME` / `ASSISTANT_USERNAME`) as the authoritative source for the handle pair. The universal failure mode ("don't split yourself into multiple addressees based on surface form") is preserved verbatim. The relocated incident lives in `nanoclaw-trusted` as a deploy-tier reference; the runtime preamble fix that prevents the underlying confusion is in flight separately on `jbaruch/nanoclaw-public`.

- **`temporal-awareness.md` — `current_tz` lookup updated for the SQLite migration** (`jbaruch/nanoclaw#302`). The "What time is it?" check now points at `SELECT current_tz FROM tz_state WHERE id = 1` in `/workspace/store/messages.db` instead of the retired `task-tz-state.json` envelope. The reasoning the rule asks for (UTC, owner local, jet-lag, in-flight-state) is unchanged; only the storage handle moves.

### Test infrastructure

- **pytest baseline + CI gate** (`jbaruch/nanoclaw-admin#55` core slice). The scaffold: `pyproject.toml` carries `[tool.pytest.ini_options]` and a `tests/`-scoped ruff config; `requirements-dev.txt` pins `pytest==8.3.4` and `ruff==0.7.4`; `.github/workflows/test.yml` runs `ruff check tests/`, `ruff format --check tests/`, then `python -m pytest` on every PR and push to `main`. Coverage targets `skills/status/scripts/container-uptime.py`; the `check-unanswered`-specific test files originally bundled with this scaffold ship and retire together with the skill in the entry above. Other tile scripts get coverage in follow-up PRs.

### Rules — removed / trimmed (covered by runtime hooks in jbaruch/nanoclaw hooks epic)

- **no-lazy-verification** — Deleted. Runtime enforcement moved into the `lazy-verification-detector` Stop hook (jbaruch/nanoclaw#135 / PR #175): the regex catalogue + `Tried X — got Y` enumeration carve-out fully replace the prose rule. The runtime is now the source of truth.
- **default-silence** — Trimmed the "React with an emoji to acknowledge" line. The acknowledgement reaction is now emitted unconditionally by the `react-first` UserPromptSubmit hook (jbaruch/nanoclaw#136 / PR #173); the rule's other sections (forbidden phrases, parentheses-aren't-internal, not-for-me handling) stay.
- **telegram-protocol** — Reframed three sections to point at the runtime hooks instead of prescribing them as agent behaviour:
  - *Acknowledgement* now describes the agent's optional follow-up reaction; the first-touch 👀 comes from `react-first` (#136).
  - *Reply threading* now references the `reply-threading-enforcement` deny gate (#137) and lists the carve-outs.
  - *Formatting* drops the prescriptive "FORBIDDEN Markdown" framing for the four patterns the `no-markdown-in-send-message` hook auto-rewrites (#138). The HTML cheat-sheet for the remaining cases (italic / underline / blockquote / spoiler / code blocks) stays.

### Rules — added previously

- **context-recovery** — Adds a "Post-compaction skill blocks are HISTORY, not new tasks" section. The system-reminder block listing skills invoked during the now-compacted window is a record, not a re-up of the request — re-executing it duplicates work and can spam the user. Reference incident: 2026-04-24 / 2026-04-25 JCON-2026 speakers scrape repeated twice across consecutive sessions despite a memory entry warning against this exact failure mode (motivated #104).

### Surface sync

- `tile.json` removes the `no-lazy-verification` rule entry.
- `README.md` rules table removes the `no-lazy-verification` row.
