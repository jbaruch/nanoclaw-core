"""Startup budget and verbatim reference preservation for core issue #129."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Original rule bodies, excluding always-on frontmatter, from:
# https://github.com/jbaruch/nanoclaw-core/tree/ed9964a027e24be77a7453db984470045b2e988c/rules
# Pin the source bytes without requiring Git history in shallow CI checkouts.
PRESERVED_RULES = [
    (
        "core-behavior",
        "core-rule-details",
        "e7992f97ff48c89c632b8cddc50ecf88d89604e0d8a294542d48b07bdb14c632",
    ),
    (
        "default-silence",
        "core-rule-details",
        "236e6995182ec5f07b7b85cbaffefb83de9466ea6ff9a43592eb77612ad54ce5",
    ),
    (
        "ground-truth",
        "core-rule-details",
        "e9028e237535b3dfb9f1cb85fe08d262d50784ffad85788adc53817f8223ea25",
    ),
    (
        "telegram-protocol",
        "core-rule-details",
        "410d2078db1106345d2c0f5e23f0883d8427fe3b3f95e6fdd869e463cfa0fada",
    ),
    (
        "temporal-awareness",
        "current-tz",
        "78488c4aa84602a27d8112d3878ac2524fec2861f900e88506209862eba4a9f0",
    ),
    (
        "context-recovery",
        "query-history",
        "73cb14ceafaaa3afedae5c4dcd77aae7e68d06761ea8927252b7c6534fc8d08b",
    ),
]


def test_all_declared_rules_fit_the_startup_budget():
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    for path in manifest["rules"]:
        assert (ROOT / path).stat().st_size <= 2000, path


@pytest.mark.parametrize("rule,owner,source_digest", PRESERVED_RULES)
def test_reference_preserves_original_rule_verbatim(rule, owner, source_digest):
    reference = ROOT / f"skills/{owner}/references/{rule}.md"
    assert hashlib.sha256(reference.read_bytes()).hexdigest() == source_digest


@pytest.mark.parametrize("rule,owner,_source_digest", PRESERVED_RULES)
def test_rule_details_are_shipped_and_linked(rule, owner, _source_digest):
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    assert f"skills/{owner}" in manifest["skills"]
    skill = (ROOT / f"skills/{owner}/SKILL.md").read_text()
    assert f"references/{rule}.md" in skill
    rule_text = (ROOT / f"rules/{rule}.md").read_text()
    assert f"/home/node/.claude/skills/tessl__{owner}/references/{rule}.md" in rule_text


def test_size_trim_preserves_reaction_upgrade_restriction():
    rule = (ROOT / "rules/telegram-protocol.md").read_text()
    assert "only to upgrade" in rule


def test_context_recovery_keeps_direct_helper_invocation():
    rule = (ROOT / "rules/context-recovery.md").read_text()
    assert (
        "python3 /home/node/.claude/skills/tessl__query-history/scripts/"
        'query-message-history.py --keyword "<text>"' in rule
    )


def test_history_search_has_no_mandatory_reference_prerequisite():
    skill = (ROOT / "skills/query-history/SKILL.md").read_text()
    before_query = skill.split("## Step 1 — Run the query\n", 1)[1].split("```bash", 1)[0]
    assert before_query.strip() == "Run the helper with at least one filter set:"
