# Changelog

## 0.1.124 — 2026-07-08

### CI — bump pytest to 9.1.1 (Dependabot, `jbaruch/nanoclaw-core#63`)

Dev-toolchain pin refresh via the weekly Dependabot `pip` config: `pytest` 8.3.4 → 9.1.1 (major) in `requirements-dev.txt`. Full suite passes on 9.1.1, including with warnings-as-errors — no reliance on pytest-8 removals.

## 0.1.123 — 2026-07-08

### CI — bump pyright to 1.1.411 (Dependabot, `jbaruch/nanoclaw-core#64`)

Dev-toolchain pin refresh via the weekly Dependabot `pip` config (renewal mechanism from #53): `pyright` 1.1.408 → 1.1.411 in `requirements-dev.txt`. Zero new diagnostics on `skills/` + `tests/`.

## 0.1.122 — 2026-07-08

### CI — bump actions/setup-python to v6.3.0 (Dependabot, `jbaruch/nanoclaw-core#60`)

SHA-pin refresh via the weekly Dependabot `github-actions` config: `actions/setup-python` 5 → 6.3.0 in `test.yml`. Clears the Node 20 deprecation warning on the setup-python step.

## 0.1.121 — 2026-07-08

### CI — bump actions/checkout to v7.0.0 (Dependabot, `jbaruch/nanoclaw-core#61`)

SHA-pin refresh via the weekly Dependabot `github-actions` config (renewal mechanism from #75): `actions/checkout` 4.3.1 → 7.0.0 in `test.yml` and `publish-tile.yml`. Clears the Node 20 deprecation warning on runners.

## 0.1.120 — 2026-07-08

### Skills — move `/status` to nanoclaw-trusted (`jbaruch/nanoclaw-core#68`)

Core ships into every container, so the `/status` skill's "no access restrictions" declaration let untrusted-group participants enumerate workspace mounts, group-folder filenames, IPC presence, and container restart timing — reconnaissance the untrusted tile's security rules exist to prevent. (The task-metadata half of the original finding was already mitigated host-side: `writeTasksSnapshot` never writes `current_tasks.json` into untrusted containers.) The skill, `container-uptime.py`, and its tests now live in `jbaruch/nanoclaw-trusted` (adopted in PR `jbaruch/nanoclaw-trusted#75`, tracking issue `jbaruch/nanoclaw-trusted#71`; published as nanoclaw-trusted 0.1.87) — tile placement is host-enforced mount scope, closing the leak structurally instead of via prompt-level redaction. In trusted/main containers, where the skill still mounts, the `tessl__status` path is unchanged; untrusted groups keep `whoami` (untrusted tile) as their tier-appropriate "what can you do here" answer. Surface sync: `tile.json`, `pyrightconfig.json`, README, copilot-instructions, conftest.

## 0.1.119 — 2026-07-08
### Skills — query-history output cap + `--offset` batching (`jbaruch/nanoclaw-core#70`, `jbaruch/nanoclaw-core#73`)

`query-message-history.py` capped rows at 50 but returned full `content` per row, so a few pasted-log messages could blow the 25 KB single-tool-result budget from `rules/query-size-limits.md` — the helper violating the rule it exists to support. The serialized payload is now capped at `MAX_OUTPUT_BYTES`: over-long row content clips to `PER_ROW_CONTENT_CHARS` first (per-row `content_truncated`), then whole rows drop oldest-first (`rows_dropped`, top-level `truncated`). The over-limit error message also pointed at "OFFSET-based batching" the CLI didn't expose (#73); `--offset` now exists (negative rejected at exit 2), wired as `LIMIT ? OFFSET ?`, echoed in the `query` block. SKILL.md documents the new payload shape and the narrow-or-batch response to a truncated result. Tests cover offset paging, per-row clip, budget-cap row drops, and negative-offset rejection.
## 0.1.118 — 2026-07-07

### Docs — refresh contributor/agent docs for conditional rules, pyright, and publish behavior (`jbaruch/nanoclaw-core#76`, `jbaruch/nanoclaw-core#69`, `jbaruch/nanoclaw-core#71`)

`.github/copilot-instructions.md` and the README philosophy section predated three repo changes and actively contradicted them: `progress-updates` is conditional (`alwaysApply: false` + `applyTo:`) while both docs demanded `alwaysApply: true` on every rule; the pyright CI gate (0.1.111) was absent from the lint/test instructions and CI table; and the publish flow docs still instructed manual version bumps and a `## Unreleased` heading, fighting the stamp-and-publish pipeline (0.1.113). All three are corrected. `rules/context-recovery.md` now shows the installed-container mount path as the runnable helper command instead of the repo-relative path that fails inside consumer containers (#69). Backfilled release headings for 0.1.113–0.1.115 below (#71) — reconstructed from the merge commits, including the release that added the stamp step and then shipped unstamped.

## 0.1.117 — 2026-07-07

### Skills — document the sub-second `delta_seconds` contract in now-vs-deadline (`jbaruch/nanoclaw-core#72`)

The output contract documented `delta_seconds` as signed (>0 future, <0 past), but `int(delta.total_seconds())` truncates toward zero — a sub-second past/future delta reads `0` while `relation` still says `past`/`future` (deliberate, tested behavior; the code comment derives `relation` from the raw timedelta for exactly this reason). A consumer following the sign contract instead of `relation` could misclassify sub-second deadlines as exactly now. The script docstring and SKILL.md now state `relation` is authoritative and `delta_seconds` can be `0` for sub-second deltas; behavior is unchanged.

## 0.1.116 — 2026-07-07

### CI — pin workflow actions by commit SHA (`jbaruch/nanoclaw-core#75`)

`actions/checkout`, `actions/setup-python`, `tesslio/setup-tessl`, and `tesslio/patch-version-publish` were tag-pinned in a job holding `TESSL_TOKEN` and `contents: write` — a retargeted upstream tag could change release behavior without a reviewed repo diff. All workflow actions are now pinned to full commit SHAs with tag comments; the existing weekly Dependabot `github-actions` config is the renewal mechanism.

### CI — gate publishing on ruff, pyright, and pytest (`jbaruch/nanoclaw-core#74`)

The publish workflow triggered on every push to `main` independently of the `Test` workflow, so a broken merge commit could publish before its own tests failed. `test.yml` is now a reusable (`workflow_call`) workflow; the publish workflow runs it as a `gate` job the `publish` job `needs`. One suite definition serves PR checks and the publish gate (review feedback: no drift between duplicated step lists), and per-job least privilege keeps the pip-installed toolchain under a read-only token — only the `publish` job holds `id-token`/`contents: write` and `TESSL_TOKEN`. `test.yml` drops its `push: main` trigger; main-push coverage comes from the gate call.

## 0.1.115 — 2026-07-07

### Changed — ignore tessl consumer-side scaffolding (`jbaruch/nanoclaw-core#67`)

Backfilled entry (shipped without one): adds `.gitignore` coverage for tessl consumer-side scaffolding files so `tessl install` artifacts in a checkout don't show as untracked noise.

## 0.1.114 — 2026-07-03

### Changed — refresh coding-policy PR review workflows

Backfilled entry (shipped without one): upgrade the gh-aw `jbaruch/coding-policy` PR review workflow templates (OpenAI + Anthropic) to the latest published version.

## 0.1.113 — 2026-07-02

### CI — wire coding-policy stamp-changelog step before publish (`jbaruch/nanoclaw-core#66`)

Backfilled entry (shipped without one): adds the `jbaruch/coding-policy` stamp-changelog action immediately before `tesslio/patch-version-publish`. Authors add un-headed `### ` CHANGELOG blocks; the step writes the `## <version> — <date>` heading at publish time.

## 0.1.112 — 2026-07-02

### Changed — backfill CHANGELOG entries for released versions 0.1.109–0.1.111

Versions 0.1.109–0.1.111 shipped without CHANGELOG entries. Every released version now has a heading; the entries are reconstructed from the merge commits that produced each release. No code change.

## 0.1.111 — 2026-07-02

### Added — gate language diagnostics in CI with pyright (`jbaruch/nanoclaw-core#53`)

Adopt a pyright zero-findings gate: `pyrightconfig.json` resolves the skill-bundle layout via per-bundle `executionEnvironments`, and a `python -m pyright --warnings skills/ tests/` step runs in CI after ruff and before pytest (`--warnings` fails the step on warnings, not just errors). The first run surfaced 24 real type findings in `tests/test_query_message_history.py` — a `reportArgumentType` on a `chat_jid=None` path and 23 Optional-subscript accesses on the `dict | None` payload — fixed with explicit param typing and an `if payload is None: raise` reader, no blanket suppressions. Adds a weekly Dependabot for the pinned dev toolchain.

## 0.1.110 — 2026-07-02

### Changed — refresh coding-policy PR review workflows (`jbaruch/nanoclaw-core#55`)

Upgrade the gh-aw `jbaruch/coding-policy` PR review workflow templates to the latest published version.

## 0.1.109 — 2026-07-01

### Changed — refresh coding-policy PR review workflows (`jbaruch/nanoclaw-core#54`)

Upgrade the gh-aw `jbaruch/coding-policy` PR review workflow templates to the latest published version.

## 0.1.108 — 2026-06-15

### Skills + Rules — deterministic past/future via `now-vs-deadline` (`jbaruch/nanoclaw-core#51`)

LLMs default to treating all information as present-tense: they convert a local deadline to UTC correctly and then assert "already passed" from vibes without ever comparing the two instants. Repro (2026-06-12, `jbaruch/nanoclaw-core#51`): a flight-assist maintenance alert declared the 15:00 UTC (11:00 EDT) Hertz pickup deadline "already passed" at **13:10 UTC** — ~2h *before* it. The offset conversion was right; the comparison against `now` never happened.

- **`now-vs-deadline` skill (new)** — Hosts `scripts/now-vs-deadline.py`, a CLI helper that takes a timezone-aware `--deadline` and compares it against the real current instant, emitting single-line JSON: `relation` (`past`/`future`/`now`), signed `delta_seconds`, human `delta_text`, `deadline_elapsed`, `still_time_to_act`. `relation` is derived from the raw timedelta sign, so a sub-second delta is still past/future rather than rounded to "now". Pure `compare(now, deadline)` + `parse_deadline(str)` functions (per-test-pinned `now`, like `container-uptime`), 14 tests including the AA487 repro as a regression guard. It deliberately does **not** accept a `--now` override — the agent must never supply `now`. The comparison is **location-agnostic**: it compares instants only, so the result is offset-independent; no physical location and no `current_tz` lookup happen in core. A naive (offset-less) deadline is rejected at exit 2, since comparing it would silently assume the host timezone — the exact failure being closed.
- **`temporal-awareness.md`** — Adds a "Past vs future — compute it, don't eyeball it" section mandating that any past/future, deadline-elapsed, or "still time to act" determination be computed via the `now-vs-deadline` helper rather than inferred from prose judgment. Kept directive-only — the incident and rationale stay in this changelog per `coding-policy: context-writing-style`. Core gains no location awareness; step 1's existing `current_tz` clock lookup is unchanged.
- **Surface sync** — `tile.json` registers the skill; `README.md` rules + skills tables updated; `.github/copilot-instructions.md` repo layout lists the new skill, script, and test file.
- **Companion (trusted tile)** — The overlapping generic "anchor to real time" sentence in `nanoclaw-trusted/rules/local-context-anchoring.md` is removed there so the grounding lives once (in core); all local/location anchoring (relative-phrasing → local frame, `location_*`/`here` handling, weak-anchor surfacing) stays in trusted. Tracked together under `jbaruch/nanoclaw-core#51`; cross-ref `jbaruch/nanoclaw-trusted` at PR time.

## 0.1.107 — 2026-05-29

<!-- Accumulated entries that had piled up under a since-removed pending-changes heading; stamped under the last version they had all shipped by (range 0.1.79–0.1.107). Cross-references ("entry above/below") are within this block. -->

### Rules — `progress-updates` switched to conditional `applyTo:` (`jbaruch/nanoclaw#552`)

The `progress-updates` rule's prescription only fires when spawning background agents or other long-running tasks (>30s expected) — keeping it always-on in baseline context paid the full body cost on every turn even when the agent had no background work to launch. Per `jbaruch/coding-policy: rule-frontmatter`, switched `alwaysApply: true` → `alwaysApply: false` + `applyTo: "** — when spawning background agents or other long-running tasks (>30s expected) that may need progress updates back to chat"`. The rule body is unchanged; only the frontmatter switched. Bundled with the same split-value drift fix from the trusted-tile portion: `tile.json` now sets explicit `"alwaysApply"` on every rule entry, closing the previously-implicit/rule-file-only state that `rule-frontmatter` warns against. The other 11 core rules (`core-behavior`, `telegram-protocol`, `language-matching`, `default-silence`, `temporal-awareness`, `ground-truth`, `read-full-content`, `context-recovery`, `post-compaction-trust`, `tone-matching`, `query-size-limits`) stay always-on by design — every one governs decision quality or chat hygiene on every turn. Parallel companion PR `jbaruch/nanoclaw-trusted#49` handles 9 task-context rules in the trusted tile.

### Rules — conciseness pass tier 3 per `coding-policy: context-writing-style`

- **core-behavior** — drop "just because both forms appear" because-clause from the dual-handle section. Operative directive ("Never assign yourself to multiple roles in a single turn") stays; the rationale clause goes.
- **progress-updates** — replace "Two max for very long tasks" with "Two max for tasks beyond ~2 minutes". The `very` intensifier was carrying no constraint; the duration bound is the actual operative content.
- **read-full-content** — drop `## Why` section entirely (3 lines of meta-justification: "Truncated previews optimize for speed at the cost of correctness. Re-doing work because of a wrong decision based on incomplete content is more expensive than reading fully once. There is no valid reason to use a preview when making a decision."). The operative content sits in `## The rule` and `## Applies to`.

### Rules

- **Compression sweep on the three rules >40 lines** (`jbaruch/nanoclaw#552` step 2 of the `requires:` + compression + reorg plan) — Audit on `telegram_old-wtf` (trusted-tier baseline) measured RULES.md at 932 lines / 28 rules. The core-tile contribution is 402 lines / 12 rules. This PR compresses the three rules that exceed the `coding-policy: context-artifacts` ~25–40 line target, preserving every load-bearing fact (incident references, command contracts, distinguishing examples) and pruning redundant framing, multi-sentence elaborations of single bullets, and exhaustive enumerations:
  - `context-recovery.md` 81 → 40 lines. Folded the "The Rule" intro and the "Hard requirement" closer into a single statement each. Compressed the 6-item "Required behavior" trigger-phrase enumeration to a representative subset. Kept the full script-invocation contract, the schema reference, and the post-compaction system-reminder block guidance with its JCON-2026 incident anchor (`docs/adr/2026-04-25-jcon-scrape-repeat-and-auto-compaction-kill.md`).
  - `ground-truth.md` 54 → 41 lines. Folded "Why this matters" and "Applies to" into the lede so the same point isn't made three times. Pre-claim and post-action verification tables stay verbatim. Stale-memory paragraph stays — it's the load-bearing intersection with `coding-policy: stateful-artifacts`.
  - `telegram-protocol.md` 42 → 23 lines. Collapsed the 5-emoji reaction allowlist + the Telegram-fallback-to-👍 explanation into one paragraph (the meaning is "pick one of these or trust the runtime"). Folded the "Forbidden patterns" bullet list of `&apos;` / `&quot;` into the same paragraph as the special-character escaping rule it elaborates. Kept the `#137` / `#138` hook references, the `pin: true` / `sender` / maintenance carve-outs for reply threading, and the 2026-04-26 untrusted-group msg-1116 incident reference.

  Combined: 177 → 104 lines, -73 lines from the core-tile RULES.md prefix. Stacks on top of the prior `jbaruch/nanoclaw-admin#180` umbrella's per-rule extraction (default-silence + telegram-protocol both already compressed in the same `Unreleased` section above; this round goes further on telegram-protocol + adds the three biggest remaining rules). Companion trusted-tile PR ships the `trusted-behavior` + `no-silent-defer` half. Step 1 of #552 (`requires:` frontmatter on the host orchestrator) merged separately as `jbaruch/nanoclaw#553`; step 3 (tile reorganization + `requires:` declarations) is a follow-up PR after step 1's mechanism is deployed and observed.

### Skills — added

- **`query-history` (new)** (`jbaruch/nanoclaw-admin#181`, umbrella `jbaruch/nanoclaw-admin#180` RULES.md diet) — A minimal companion skill for the `context-recovery` rule. Hosts `scripts/query-message-history.py` — a CLI helper with `--keyword`, `--sender`, `--limit` flags, JSON-on-stdout output, and 13 tests. Replaces the inlined Python snippets that lived in `rules/context-recovery.md`. The script enforces three correctness contracts the inlined snippets did not: (a) `escape_like` + `LIKE … ESCAPE '\\'` so user-supplied `%` / `_` / `\` characters match literally instead of acting as wildcards; (b) `--limit` capped at 50 rows per `rules/query-size-limits.md` (rejected at exit 2 with a pointer to that rule); (c) read-only DB open via `file:…?mode=ro` URI so a missing/mistyped `NANOCLAW_DB` fails fast instead of silently creating an empty SQLite file. `tessl skill review skills/query-history` reports 86% (threshold 85). Originally proposed against `skills/check-unanswered/scripts/` in PR #40 v1; that skill was retired in `nanoclaw-core#39` while this PR was open — query-history is the new home and the rule reference (`/home/node/.claude/skills/tessl__query-history/scripts/query-message-history.py`) follows.

### Rules

- **`context-recovery.md` — migrate JCON-2026 / `jbaruch/nanoclaw#104` postmortem to `docs/adr/`** (`jbaruch/nanoclaw-admin#183` core-half, umbrella `jbaruch/nanoclaw-admin#180` RULES.md diet) — The "Post-compaction skill blocks are HISTORY" section's reference-incident paragraph (the JCON-2026 scrape repeat 2026-04-24 / 2026-04-25 + the auto-compaction-kill motivation) loaded into every spawn but only fires the agent's recognition once the per-turn gate is already engaged. Move to `docs/adr/2026-04-25-jcon-scrape-repeat-and-auto-compaction-kill.md`. The rule keeps the per-turn gate (the three-step verification: read Current Work + Optional Next Step, read most recent user message, ask before re-executing visible side effects) and a 1-line past-failure anchor citing the ADR. Verbatim transfer; no spec content changes. Measured: rule drops 5,841 → 5,552 bytes (-289). Companion trusted-half PR migrates the dual-handle and installed-content-immutable postmortems.

- **`default-silence.md` + `telegram-protocol.md` — bundled compression** (`jbaruch/nanoclaw-admin#180` core-tile bundled-cleanup half) — Per the umbrella's per-rule split:
  - `default-silence.md`: 22-item forbidden-phrases enumeration (each one a specific surface form of "I narrated my non-action") collapses to one imperative naming the *pattern*. The "Every form of 'I decided not to respond' IS the leak" 5-bullet sub-list inside the not-for-me section was duplicating the same shape — also folded into one sentence. The runtime gate (zero output in passive chats; never narrate non-action) and the `<internal>`-vs-parens reminder stay. Drop: 4,975 → 3,939 bytes (-1,036).
  - `telegram-protocol.md`: 73-emoji reaction allowlist drops to a one-line statement that `react_to_message` validates and falls back to 👍 — agents don't need the table loaded into every spawn since the tool side handles invalid input. The 7-row HTML cheatsheet (italic / underline / strikethrough / code block / code-block-with-lang / quote / spoiler) collapses to an inline tag list. Most tags (`<i>`, `<u>`, `<s>`, `<pre>`, `<blockquote>`) are standard HTML; `<tg-spoiler>` is Telegram-specific and called out as such in the rule. The code-block-with-lang example keeps a concrete language token (`<code class="language-python">`) rather than a placeholder, so models don't copy `language-…` verbatim. The hook-rewrite reference for the four common Markdown leaks stays. Drop: 3,496 → 2,839 bytes (-657).
  - Combined: -1,693 bytes from the core-tile prefix, on top of the targeted-extraction PRs (#181, #183-core).

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
