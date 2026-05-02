# Copilot Instructions — jbaruch/nanoclaw-core

## What This Repository Is

`jbaruch/nanoclaw-core` is a **tessl tile** — a publishable package of behavioral rules and skills for NanoClaw personal assistant agents. It is installed into NanoClaw agent environments via `tessl install jbaruch/nanoclaw-core`. The tile provides always-on conversational rules and reusable skill scripts.

**Current version:** see `tile.json` → `version` field.

---

## Repository Layout

```
tile.json                    # Tile manifest: name, version, rules/skills registry
README.md                    # Human-readable overview + rules/skills tables
CHANGELOG.md                 # Version history and unreleased changes
pyproject.toml               # pytest config + ruff lint (scoped to tests/ only)
requirements-dev.txt         # Dev dependencies: pytest==8.3.4, ruff==0.7.4

rules/                       # 12 always-on behavioral rule files (Markdown)
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

tests/
  conftest.py               # Shared fixtures; loads kebab-case scripts via importlib
  test_container_uptime.py

.github/
  workflows/
    test.yml                # CI: ruff lint + pytest on every PR and push to main
    publish-tile.yml        # Publish tile to tessl registry on push to main
    review-openai.yml/.md   # AI-assisted PR review (OpenAI)
    review-anthropic.yml/.md# AI-assisted PR review (Anthropic)
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

**Run tests:**

```bash
python -m pytest
```

CI runs these in order: ruff check → ruff format → pytest. All three must pass on every PR.

**There is no build step.** This is a pure Python + Markdown tile; nothing needs compiling.

---

## Key Conventions

### Rule files (`rules/*.md`)

- Every rule file **must** have YAML frontmatter with `alwaysApply: true` as the first thing in the file:
  ```markdown
  ---
  alwaysApply: true
  ---
  ```
- One concern per rule file — keep rules focused so consumers can override surgically.
- Rule filenames are kebab-case (e.g., `core-behavior.md`).

### Skill files (`skills/*/SKILL.md`)

- SKILL.md files have YAML frontmatter with `name:` and `description:` fields (no `alwaysApply`).
- Scripts live in `skills/<skill-name>/scripts/` and use kebab-case filenames (e.g., `container-uptime.py`).
- Skill scripts are plain Python; they are deployed into agent containers at a known path: `/home/node/.claude/skills/tessl__<skill-name>/scripts/<script>.py`.

### `tile.json` and `README.md` must stay in sync

- Whenever a rule is added or removed, update both `tile.json` (the `rules` object) and the rules table in `README.md`.
- Whenever a skill is added or removed, update both `tile.json` (the `skills` object) and the skills table in `README.md`.
- The `version` field in `tile.json` follows semver; bump it for every change published to the tessl registry.

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
| `test.yml` | PR + push to `main` | Lint (`ruff`) + `pytest` |
| `publish-tile.yml` | push to `main`, `workflow_dispatch` | tessl skill review (quality gate ≥85) + tile publish |
| `review-openai.md` / `review-anthropic.md` | PR events | AI-assisted code review |

The publish workflow runs `tessl skill review --threshold 85` on each skill before publishing. A failing quality score blocks the publish.

---

## Common Gotchas / Lessons Learned

1. **`tile.json` + `README.md` drift** — if you add/remove a rule or skill in one place, update both. The table and the JSON registry must match.
2. **Ruff scope** — ruff is intentionally limited to `tests/`. Do not widen it to `skills/*/scripts/` without an explicit decision in the PR.
3. **Frontmatter required** — rule files without `alwaysApply: true` frontmatter will not be applied by the tessl runtime. Always include it.
4. **Kebab script loading** — if you add a new skill script and need to test it, add a fixture to `conftest.py` following the `_load()` pattern. Do not try to import the script directly.
5. **Uniform JSON payload shape** — any new skill script that outputs JSON must guarantee all documented keys are present on every code path, including error paths.
6. **Version bump** — increment `tile.json` version for any change intended to be published. The publish workflow does not auto-bump it.
7. **CHANGELOG.md** — document unreleased changes under `## Unreleased` before they land in a release section.
