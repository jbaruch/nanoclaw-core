# Copilot Instructions — jbaruch/nanoclaw-core

## What This Repository Is

`jbaruch/nanoclaw-core` is a **tessl tile** — a publishable package of behavioral rules and skills for NanoClaw personal assistant agents. It is installed into NanoClaw agent environments via `tessl install jbaruch/nanoclaw-core`. The tile provides always-on conversational rules and reusable skill scripts.

**Current version:** see `tile.json` → `version` field.

---

## Repository Layout

```
tile.json                    # Tile manifest: name, version, rules/skills registry
README.md                    # Human-readable overview + rules/skills tables
CHANGELOG.md                 # Version history; un-headed `### ` blocks at the top
                             # are stamped with the version heading at publish
pyproject.toml               # pytest config + ruff lint (scoped to tests/ only)
pyrightconfig.json           # pyright module resolution for the skill-bundle layout
requirements-dev.txt         # Dev dependencies: pyright, pytest, ruff (pinned)

rules/                       # 12 behavioral rule files (11 always-on, 1 conditional)
  core-behavior.md
  telegram-protocol.md
  default-silence.md
  ground-truth.md
  context-recovery.md
  post-compaction-trust.md
  tone-matching.md
  language-matching.md
  temporal-awareness.md
  read-full-content.md
  query-size-limits.md
  progress-updates.md

skills/
  status/
    SKILL.md                 # Skill definition consumed by the tessl runtime
    scripts/
      container-uptime.py   # Reads /.dockerenv mtime to compute container uptime
  query-history/
    SKILL.md
    scripts/
      query-message-history.py  # Keyword/sender search over messages.db
  now-vs-deadline/
    SKILL.md
    scripts/
      now-vs-deadline.py    # Deterministic past/future comparison vs the current instant

tests/
  conftest.py               # Shared fixtures; loads kebab-case scripts via importlib
  test_container_uptime.py
  test_query_message_history.py
  test_now_vs_deadline.py

.github/
  workflows/
    test.yml                # CI: ruff + pyright + pytest on every PR; callable
                            # (workflow_call) as the publish workflow's gate job
    publish-tile.yml        # On push to main: test-suite gate, skill review,
                            # tile lint, CHANGELOG stamp, publish to tessl registry
    review-openai.md        # AI-assisted PR review (OpenAI; compiled .lock.yml)
    review-anthropic.md     # AI-assisted PR review (Anthropic; compiled .lock.yml)
```

---

## How to Lint, Build, and Test

Install dev dependencies first (Python 3.11+):

```bash
pip install -r requirements-dev.txt
```

**Lint** (scoped to `tests/` only — tile scripts under `skills/*/scripts/` predate the lint config):

```bash
python -m ruff check tests/
python -m ruff format --check tests/
```

**Type check** (zero-findings gate; `--warnings` fails on warnings too; module resolution via `pyrightconfig.json`):

```bash
python -m pyright --warnings skills/ tests/
```

**Run tests:**

```bash
python -m pytest
```

CI runs these in order: ruff check → ruff format → pyright → pytest. All four must pass on every PR.

**There is no build step.** This is a pure Python + Markdown tile; nothing needs compiling.

---

## Key Conventions

### Rule files (`rules/*.md`)

- Every rule file **must** open with YAML frontmatter declaring its scope. Always-on rules (the default here — 11 of 12) use:
  ```markdown
  ---
  alwaysApply: true
  ---
  ```
- Conditional rules use `alwaysApply: false` plus an `applyTo:` glob+prose scope (see `rules/progress-updates.md` for the live example). Both forms are valid tessl frontmatter; pick by whether the rule's prescription fires on every turn or only in a specific context.
- One concern per rule file — keep rules focused so consumers can override surgically.
- Rule filenames are kebab-case (e.g., `core-behavior.md`).

### Skill files (`skills/*/SKILL.md`)

- SKILL.md files have YAML frontmatter with `name:` and `description:` fields (no `alwaysApply`).
- Scripts live in `skills/<skill-name>/scripts/` and use kebab-case filenames (e.g., `container-uptime.py`).
- Skill scripts are plain Python; they are deployed into agent containers at a known path: `/home/node/.claude/skills/tessl__<skill-name>/scripts/<script>.py`.

### `tile.json` and `README.md` must stay in sync

- Whenever a rule is added or removed, update both `tile.json` (the `rules` object) and the rules table in `README.md`.
- Whenever a skill is added or removed, update both `tile.json` (the `skills` object) and the skills table in `README.md`.
- The `version` field in `tile.json` follows semver. The publish workflow bumps the patch version automatically on every merge to `main`; edit it by hand only for an intentional minor or major release (see gotcha 6).

### Tests

- Test files live in `tests/` and are standard pytest.
- **Kebab-case script files cannot be imported normally** (`import container-uptime` is a syntax error). All test fixtures load them via `importlib.util.spec_from_file_location`. The `conftest.py` `_load()` helper handles this — use the existing `container_uptime` fixture as the template rather than reimplementing the loading pattern.
- Each fixture returns a **fresh module instance per test** — this prevents module-level constants from leaking across tests that monkeypatch them.
- Tests must be deterministic: no random test data, no reliance on current wall-clock time. Pin time inputs explicitly (see `test_container_uptime.py` for the pattern).
- Ruff lint is scoped to `tests/` in `pyproject.toml`; do **not** apply ruff rules to files under `skills/*/scripts/` unless that is the explicit scope of a PR.

### Python script conventions

- Scripts output JSON to stdout. The payload shape must have **all keys present on both success and error paths** — downstream consumers parse uniformly without special-casing.
- The `error` field uses three states: `null` (clean success), `"env-warning: ..."` prefix (non-fatal config hint, script still produced useful output), or any other string (hard failure, exits non-zero).

---

## CI / Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `test.yml` | PR + `workflow_call` | Lint (`ruff`) + type check (`pyright`) + `pytest` |
| `publish-tile.yml` | push to `main`, `workflow_dispatch` | gate (calls `test.yml`) → tessl skill review (quality gate ≥85) → tile lint → CHANGELOG stamp → publish |
| `review-openai.md` / `review-anthropic.md` | PR events | AI-assisted code review |

The publish workflow first runs the full test suite as a read-only `gate` job (calling `test.yml` via `workflow_call` — main-push coverage comes from this call, not a separate `push:` trigger on `test.yml`), then `tessl skill review --threshold 85` on each changed skill. A red suite or failing quality score blocks the publish.

---

## Common Gotchas / Lessons Learned

1. **`tile.json` + `README.md` drift** — if you add/remove a rule or skill in one place, update both. The table and the JSON registry must match.
2. **Ruff scope** — ruff is intentionally limited to `tests/`. Do not widen it to `skills/*/scripts/` without an explicit decision in the PR.
3. **Frontmatter required** — rule files without scope frontmatter will not be applied by the tessl runtime. Always include either `alwaysApply: true` or `alwaysApply: false` + `applyTo:` (conditional).
4. **Kebab script loading** — if you add a new skill script and need to test it, add a fixture to `conftest.py` following the `_load()` pattern. Do not try to import the script directly.
5. **Uniform JSON payload shape** — any new skill script that outputs JSON must guarantee all documented keys are present on every code path, including error paths.
6. **Version bump** — the publish workflow auto-bumps the patch version via `tesslio/patch-version-publish` on every merge to `main`. Only edit `tile.json`'s version by hand for a minor or major bump.
7. **CHANGELOG.md** — no `## Unreleased` heading. Add un-headed `### ` entry blocks at the top; the publish workflow's stamp step writes the `## <version> — <date>` heading at publish time. Every merge publishes a version, so every PR should carry an entry block.
