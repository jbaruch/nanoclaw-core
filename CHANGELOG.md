# Changelog

## Unreleased

### Test infrastructure

- **pytest baseline + CI gate** (new) — Mirrors the `nanoclaw-admin#59` / `nanoclaw-trusted#11` scaffold: `pyproject.toml` carries `[tool.pytest.ini_options]` and a `tests/`-scoped ruff config; `requirements-dev.txt` pins `pytest==8.3.4` and `ruff==0.7.4`; `.github/workflows/test.yml` runs `ruff check tests/`, `ruff format --check tests/`, then `python -m pytest` on every PR and push to `main`. Initial coverage targets `skills/check-unanswered/scripts/check-unanswered.py` per the issue: `_make_payload` shape contract (every key present on success and error paths), the `env-warning:` prefix path through `_merge_env_warnings`, and `main()`'s missing-`NANOCLAW_CHAT_JID` early-exit. Closes the core slice of `nanoclaw-admin#55`. Other tile scripts get coverage in follow-up PRs.

### Rules — removed / trimmed (covered by runtime hooks in qwibitai/nanoclaw hooks epic)

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
