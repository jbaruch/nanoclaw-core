"""Regressions for the rule trim's installed read gates and retained boundaries."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE_ROOT = "/home/node/.claude/skills/tessl__"
MOVED = [
    ("core-behavior", "core-behavior"),
    ("default-silence", "core-behavior"),
    ("telegram-protocol", "core-behavior"),
    ("ground-truth", "core-behavior"),
    ("temporal-awareness", "current-tz"),
    ("context-recovery", "query-history"),
]


def test_all_declared_rules_fit_the_startup_budget():
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    for path in manifest["rules"]:
        assert (ROOT / path).stat().st_size <= 2000, path


@pytest.mark.parametrize(("rule", "skill"), MOVED)
def test_moved_contract_has_a_native_full_read_gate_and_shipped_target(rule: str, skill: str):
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    native = f"{NATIVE_ROOT}{skill}/references/{rule}.md"
    text = (ROOT / f"rules/{rule}.md").read_text()
    assert native in text and "in full" in text
    assert "Missing or unreadable" in text or "missing or unreadable" in text
    assert "never" in text and "`@`" in text
    assert f"skills/{skill}" in manifest["skills"]
    reference = ROOT / f"skills/{skill}/references/{rule}.md"
    assert reference.is_file() and not reference.is_symlink()
    assert native in (ROOT / f"skills/{skill}/SKILL.md").read_text()
    # The publisher includes declared skill trees, including references.
    ignored = (ROOT / ".tesslignore").read_text().splitlines()
    assert "skills/" not in ignored and "references/" not in ignored
    assert str(reference.relative_to(ROOT)) not in ignored


def test_every_native_pointer_in_shipped_prose_resolves_to_a_declared_regular_file():
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    paths = [*ROOT.glob("rules/*.md"), *ROOT.glob("skills/**/*.md")]
    for source in paths:
        text = source.read_text()
        for skill, suffix in re.findall(re.escape(NATIVE_ROOT) + r"([\w-]+)/([\w/.-]+)", text):
            assert f"skills/{skill}" in manifest["skills"], source
            target = ROOT / "skills" / skill / suffix
            assert target.is_file() and not target.is_symlink(), (source, target)
            assert target.resolve().is_relative_to(ROOT / "skills" / skill)
        assert not re.search(r"`skills/[\w-]+/references/[\w.-]+\.md", text), source


def test_silent_relevance_decision_is_complete_before_any_reference_read():
    text = (ROOT / "rules/default-silence.md").read_text()
    decision, gate = text.split("## Required Read After Relevance")
    for boundary in (
        "without tools",
        "no text, tool call, reaction or `<internal>` tags",
        "Every main-chat message",
        "Direct address requires a response",
        "private 1:1",
        "Jev outage",
        "delivery proves no relevance",
        "zero output is valid",
        "requires_trigger=0",
        "staying out would clearly be a miss",
    ):
        assert boundary in decision
    assert NATIVE_ROOT not in decision
    assert "Before acting on a relevant message or scheduled wake" in gate
    reference = (ROOT / "skills/core-behavior/references/default-silence.md").read_text()
    assert "## How a message reached you" not in reference
    assert "## Triggered and untriggered chats" not in reference


def test_script_contracts_have_one_canonical_prose_location():
    history = (ROOT / "skills/query-history/SKILL.md").read_text()
    recovery = (ROOT / "skills/query-history/references/context-recovery.md").read_text()
    zone_skill = (ROOT / "skills/current-tz/SKILL.md").read_text()
    zone_reference = (ROOT / "skills/current-tz/references/temporal-awareness.md").read_text()
    assert "python3 " + NATIVE_ROOT + "query-history/scripts/query-message-history.py" in history
    assert "--keyword" not in recovery and "--limit" not in recovery
    assert NATIVE_ROOT + "query-history/SKILL.md" in recovery
    assert "python3 " + NATIVE_ROOT + "current-tz/scripts/read-current-tz.py" in zone_reference
    assert "```bash" not in zone_skill and "Stdout" not in zone_skill
    assert "Scoped current-zone script contract" in zone_skill


def test_scheduled_wake_citation_names_the_reference_heading():
    source = (ROOT / "skills/core-behavior/references/core-behavior.md").read_text()
    target = (ROOT / "skills/core-behavior/references/default-silence.md").read_text()
    assert NATIVE_ROOT + "core-behavior/references/default-silence.md` Scheduled wakes" in source
    assert "## Scheduled wakes" in target
