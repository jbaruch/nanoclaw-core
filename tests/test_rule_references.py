"""Startup budget and skill-owned reference links for core issue #129."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

RULE_REFERENCES = [
    ("core-behavior", "core-rule-details"),
    ("default-silence", "core-rule-details"),
    ("ground-truth", "core-rule-details"),
    ("telegram-protocol", "core-rule-details"),
    ("temporal-awareness", "current-tz"),
    ("context-recovery", "query-history"),
]


def test_all_declared_rules_fit_the_startup_budget():
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    for path in manifest["rules"]:
        assert (ROOT / path).stat().st_size <= 2000, path


@pytest.mark.parametrize("rule,owner", RULE_REFERENCES)
def test_rule_details_are_shipped_and_linked(rule, owner):
    reference = ROOT / f"skills/{owner}/references/{rule}.md"
    assert reference.is_file()
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    assert f"skills/{owner}" in manifest["skills"]
    skill = (ROOT / f"skills/{owner}/SKILL.md").read_text()
    assert f"references/{rule}.md" in skill
    rule_text = (ROOT / f"rules/{rule}.md").read_text()
    assert f"/home/node/.claude/skills/tessl__{owner}/references/{rule}.md" in rule_text


def test_size_trim_preserves_reaction_upgrade_restriction():
    rule = (ROOT / "rules/telegram-protocol.md").read_text()
    assert "only to upgrade" in rule


def test_harness_nudge_is_a_scoped_internal_only_narration_exception():
    rule = (ROOT / "rules/default-silence.md").read_text()
    scheduled = rule.split("## Scheduled wakes\n", 1)[1].split("\n## ", 1)[0]
    assert "- Narrow exception for the harness nudge.\n" in scheduled
    exception = scheduled.split("- Narrow exception for the harness nudge.\n", 1)[1]
    preconditions, reset = exception.split("\n- ", 1)
    scope, response, delivery = preconditions.splitlines()
    assert scope.startswith("  1. ")
    assert "The user hasn't heard from you in a while" in scope
    assert "say in a few words what you're doing” is not a user message" in scope
    assert response == "  2. Use one `<internal>` line; keep working."
    assert delivery == "  3. No plain text, `send_message` or reactions in any session or chat."
    assert reset.startswith(
        "In every other case, never narrate work or decisions not to respond, "
        "in any language or notation."
    )
    assert "- Never narrate work or decisions not to respond" not in rule


def test_threading_bypasses_do_not_exempt_user_responses():
    rule = (ROOT / "rules/telegram-protocol.md").read_text()
    threading = rule.split("## Reply threading\n", 1)[1].split("\n## ", 1)[0]
    bullets = [line for line in threading.splitlines() if line.startswith("- ")]
    hook = next(line for line in bullets if "`reply-threading-enforcement`" in line)
    assert all(term in hook for term in ("`pin: true`", "`sender`", "maintenance"))
    responses = next(line for line in bullets if "Every response to a user message" in line)
    assert "`reply_to`" in responses
    assert '<message id="...">' in responses
    assert "unsolicited output may stand alone" in responses


def test_context_recovery_routes_helper_contract_to_skill():
    rule = (ROOT / "rules/context-recovery.md").read_text()
    skill = (ROOT / "skills/query-history/SKILL.md").read_text()
    helper = "scripts/query-message-history.py"
    assert 'Skill(skill: "query-history")' in rule
    assert helper not in rule
    assert helper in skill


def test_history_search_has_no_mandatory_reference_prerequisite():
    skill = (ROOT / "skills/query-history/SKILL.md").read_text()
    before_query = skill.split("## Step 1 — Run the query\n", 1)[1].split("```bash", 1)[0]
    assert before_query.strip() == "Run the helper with at least one filter set:"
