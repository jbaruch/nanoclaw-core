"""Startup byte budget for manifest-declared rules."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_all_declared_rules_fit_the_startup_budget():
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    for path in manifest["rules"]:
        assert (ROOT / path).stat().st_size <= 2000, path


@pytest.mark.parametrize(
    "directive",
    [
        "Decide relevance without tools",
        "A transport retry demanding visible output does not change relevance",
        "Unknown/unavailable mode uses the triggered standard",
    ],
)
def test_size_trim_does_not_add_relevance_policy(directive):
    rule = (ROOT / "rules/default-silence.md").read_text()
    assert directive not in rule
    assert "not for you gets zero output" in rule


def test_size_trim_preserves_reaction_upgrade_restriction():
    rule = (ROOT / "rules/telegram-protocol.md").read_text()
    assert "only to upgrade" in rule


def test_current_tz_keeps_discovery_and_caller_contract():
    skill = (ROOT / "skills/current-tz/SKILL.md").read_text()
    assert "deciding whether a local time has passed" in skill
    assert "Exit codes:" in skill
    assert "## Step 2 — Act on the result" in skill
    assert "Never read `home_tz` as a stand-in" in skill
