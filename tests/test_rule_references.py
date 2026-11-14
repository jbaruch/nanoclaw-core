"""Regressions for the rule trim's installed read gates and retained boundaries."""

import hashlib
import json
import re
import shutil
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


@pytest.fixture
def installed_plugin(tmp_path):
    """Mirror nanoclaw ef8cf4d src/volume-mounts.ts:715-759, 830-834.

    Match the fleet's travel/trusted installed-layout acceptance fixtures.
    Native Read-tool acceptance is documented in tests/README.md.
    """
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    native = tmp_path / "home/node/.claude"
    for skill in manifest["skills"]:
        shutil.copytree(ROOT / skill, native / "skills" / f"tessl__{Path(skill).name}")
    startup = native / ".tessl/RULES.md"
    startup.parent.mkdir(parents=True)
    startup.write_text("\n\n---\n\n".join((ROOT / rule).read_text() for rule in manifest["rules"]))
    return tmp_path, native, startup


def test_all_declared_rules_fit_the_startup_budget():
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    for path in manifest["rules"]:
        assert (ROOT / path).stat().st_size <= 2000, path


@pytest.mark.parametrize(("rule", "skill"), MOVED)
def test_moved_contract_has_a_native_full_read_gate_and_shipped_target(
    installed_plugin, rule: str, skill: str
):
    root, installed, startup = installed_plugin
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    native = f"{NATIVE_ROOT}{skill}/references/{rule}.md"
    text = (ROOT / f"rules/{rule}.md").read_text()
    assert text in startup.read_text()
    assert native in text and "in full" in text
    assert "native Read tool" in text
    assert "Missing or unreadable" in text or "missing or unreadable" in text
    assert "never" in text and "`@`" in text
    assert f"skills/{skill}" in manifest["skills"]
    reference = root / native.lstrip("/")
    assert reference.is_file() and not reference.is_symlink()
    assert reference.read_bytes() == (ROOT / f"skills/{skill}/references/{rule}.md").read_bytes()
    assert native in (installed / f"skills/tessl__{skill}/SKILL.md").read_text()
    # The publisher includes declared skill trees, including references.
    ignored = (ROOT / ".tesslignore").read_text().splitlines()
    assert "skills/" not in ignored and "references/" not in ignored
    assert f"skills/{skill}/references/{rule}.md" not in ignored


def test_every_native_pointer_resolves_in_the_installed_session(installed_plugin):
    root, installed, startup = installed_plugin
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    paths = [startup, *(installed / "skills").rglob("*.md")]
    for source in paths:
        text = source.read_text()
        for skill, suffix in re.findall(re.escape(NATIVE_ROOT) + r"([\w-]+)/([\w/.-]+)", text):
            assert f"skills/{skill}" in manifest["skills"], source
            target = root / f"{NATIVE_ROOT}{skill}/{suffix}".lstrip("/")
            assert target.is_file() and not target.is_symlink(), (source, target)
            assert target.resolve().is_relative_to(installed / "skills" / f"tessl__{skill}")


@pytest.mark.parametrize(
    ("rule", "skill", "size", "digest"),
    [
        (
            "core-behavior",
            "core-behavior",
            2191,
            "e7992f97ff48c89c632b8cddc50ecf88d89604e0d8a294542d48b07bdb14c632",
        ),
        (
            "default-silence",
            "core-behavior",
            4013,
            "236e6995182ec5f07b7b85cbaffefb83de9466ea6ff9a43592eb77612ad54ce5",
        ),
        (
            "telegram-protocol",
            "core-behavior",
            2997,
            "410d2078db1106345d2c0f5e23f0883d8427fe3b3f95e6fdd869e463cfa0fada",
        ),
        (
            "ground-truth",
            "core-behavior",
            2252,
            "e9028e237535b3dfb9f1cb85fe08d262d50784ffad85788adc53817f8223ea25",
        ),
        (
            "temporal-awareness",
            "current-tz",
            4769,
            "78488c4aa84602a27d8112d3878ac2524fec2861f900e88506209862eba4a9f0",
        ),
        (
            "context-recovery",
            "query-history",
            3545,
            "73cb14ceafaaa3afedae5c4dcd77aae7e68d06761ea8927252b7c6534fc8d08b",
        ),
    ],
)
def test_installed_references_retain_every_original_clause(
    installed_plugin, rule: str, skill: str, size: int, digest: str
):
    # Independent complete bodies from ed9964a:rules/<rule>.md, excluding
    # only frontmatter. Supplementary installed-path/schema detail follows.
    # No git history or checkout-relative lookup is needed in an installed session.
    _, installed, _ = installed_plugin
    reference = installed / f"skills/tessl__{skill}/references/{rule}.md"
    assert hashlib.sha256(reference.read_bytes()[:size]).hexdigest() == digest


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
        "transport retry demanding visible output does not change message relevance",
    ):
        assert boundary in decision
    assert NATIVE_ROOT not in decision
    assert "Before acting on a relevant message or scheduled wake" in gate
    reference = (ROOT / "skills/core-behavior/references/default-silence.md").read_text()
    assert "Read this reference only after deciding to engage" in reference
    assert "do not require a read on the not-for-me path" in reference


def test_unavailable_chat_policy_preserves_conservative_join_permission(installed_plugin):
    _, installed, startup = installed_plugin
    # Untrusted runtime projections omit registered_groups. A useful room
    # question must still be answerable under the original triggered standard.
    assert (
        "If authoritative `requires_trigger` is unavailable, use the triggered-chat standard; "
        "no successful lookup is required."
    ) in startup.read_text()
    reference = (
        installed / "skills/tessl__core-behavior/references/default-silence.md"
    ).read_text()
    assert "Before joining indirectly, verify" not in startup.read_text()
    assert "Stop the affected join" not in reference


def test_script_contracts_have_one_canonical_prose_location():
    history = (ROOT / "skills/query-history/SKILL.md").read_text()
    recovery = (ROOT / "skills/query-history/references/context-recovery.md").read_text()
    zone_skill = (ROOT / "skills/current-tz/SKILL.md").read_text()
    zone_reference = (ROOT / "skills/current-tz/references/temporal-awareness.md").read_text()
    assert "python3 " + NATIVE_ROOT + "query-history/scripts/query-message-history.py" in recovery
    assert "--keyword" in recovery and "--limit" in recovery
    assert "```bash" not in history and "--limit" not in history
    assert NATIVE_ROOT + "query-history/references/context-recovery.md" in history
    assert "python3 " + NATIVE_ROOT + "current-tz/scripts/read-current-tz.py" in zone_reference
    assert "```bash" not in zone_skill and "Stdout" not in zone_skill
    assert "Scoped current-zone script contract" in zone_skill


def test_scheduled_wake_citation_names_the_reference_heading():
    source = (ROOT / "skills/core-behavior/references/core-behavior.md").read_text()
    target = (ROOT / "skills/core-behavior/references/default-silence.md").read_text()
    assert NATIVE_ROOT + "core-behavior/references/default-silence.md` Scheduled wakes" in source
    assert "## Scheduled wakes" in target
