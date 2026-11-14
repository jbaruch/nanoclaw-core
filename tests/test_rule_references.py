"""Startup byte budget for manifest-declared rules."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_all_declared_rules_fit_the_startup_budget():
    manifest = json.loads((ROOT / ".tessl-plugin/plugin.json").read_text())
    for path in manifest["rules"]:
        assert (ROOT / path).stat().st_size <= 2000, path
