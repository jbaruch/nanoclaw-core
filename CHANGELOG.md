# Changelog

## Unreleased

### Rules

- **`temporal-awareness.md` — `current_tz` lookup updated for the SQLite migration** (`jbaruch/nanoclaw#302`). The "What time is it?" check now points at `SELECT current_tz FROM tz_state WHERE id = 1` in `/workspace/store/messages.db` instead of the retired `task-tz-state.json` envelope. The reasoning the rule asks for (UTC, owner local, jet-lag, in-flight-state) is unchanged; only the storage handle moves.

### Test infrastructure

- **`unanswered-precheck.py` backfill (`nanoclaw-admin#123` core slice)** — Closes the core half of the test-coverage ramp tracked in `jbaruch/nanoclaw-admin#123`. The script already had `main()` + entry-point guard, so this is a pure test PR with no script changes. 16 tests cover the documented contract: legacy seen-state migration (no-op when legacy absent / move-to-canonical when only legacy / drop-legacy when both exist / OSError → stderr-warn-but-continue per the "best-effort heuristic" comment), the three subprocess failure modes — exit non-zero → `wakeAgent: True` with stderr tail; JSONDecodeError → `bad JSON from check-unanswered` error; bad `unanswered` shape (covered by three parametrized variants — not-a-list, list-of-strings, dicts-missing-`id`) → `bad unanswered shape` rather than the `m['id']` crash this script exists to prevent, the decision logic (no-prev-state → all current treated as new, exact-match prev set → `wakeAgent: False` with NO `data` field, partial-overlap → only delta counted in `new_count`, corrupt seen-file → `prev_ids = []` reset, atomic seen-file write persisted with no `.unanswered-seen-*` orphans), `env-warning:` passthrough into `data.env_warning` independent of the wake decision (carries even when `wakeAgent: False`), and the `os.replace`-OSError path → `wakeAgent: True` + `data.error: "seen-file write failed: ..."` rather than crashing (the silent-precheck-failure baseline that gates this script's wake decision). New `unanswered_precheck` conftest fixture redirects all four module-level paths (`SEEN_STATE_DIR`, `SEEN_FILE`, `LEGACY_SEEN_FILE`, `CHECK_SCRIPT`) at tmp_path; tests write fake check-unanswered.py stubs into the redirected `CHECK_SCRIPT` location to drive each failure mode without invoking the real subprocess. Total tile suite now 36 passing (was 20). With this slice, `jbaruch/nanoclaw-admin#123` is fully closed across both tiles.

- **pytest baseline + CI gate** (new) — Mirrors the `nanoclaw-admin#59` / `nanoclaw-trusted#11` scaffold: `pyproject.toml` carries `[tool.pytest.ini_options]` and a `tests/`-scoped ruff config; `requirements-dev.txt` pins `pytest==8.3.4` and `ruff==0.7.4`; `.github/workflows/test.yml` runs `ruff check tests/`, `ruff format --check tests/`, then `python -m pytest` on every PR and push to `main`. Initial coverage targets `skills/check-unanswered/scripts/check-unanswered.py` per the issue: `_make_payload` shape contract (every key present on success and error paths), the `env-warning:` prefix path through `_merge_env_warnings`, and `main()`'s missing-`NANOCLAW_CHAT_JID` early-exit. Closes the core slice of `nanoclaw-admin#55`. Other tile scripts get coverage in follow-up PRs.

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
