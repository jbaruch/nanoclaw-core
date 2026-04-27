"""Baseline tests for skills/check-unanswered/scripts/check-unanswered.py.

Coverage focuses on the two contracts the precheck and the skill
both depend on for uniform JSON output (per issue
jbaruch/nanoclaw-admin#55, core slice):

  1. **_make_payload shape** — every key present on both success
     and error paths so downstream consumers don't have to special-case
     error JSON.
  2. **env-warning path** — bad LOOKBACK_HOURS / CONTEXT_CAP /
     CHECK_UNANSWERED_GRACE_SECONDS surfaces with an `env-warning:`
     prefix in the payload's `error` field, alongside any primary
     hard error.
"""

import json


def test_parse_int_env_valid(check_unanswered, monkeypatch):
    monkeypatch.setenv("FOO_INT", "42")
    val, err = check_unanswered._parse_int_env("FOO_INT", 7)
    assert val == 42
    assert err is None


def test_parse_int_env_missing_returns_default(check_unanswered, monkeypatch):
    monkeypatch.delenv("MISSING_FOO", raising=False)
    val, err = check_unanswered._parse_int_env("MISSING_FOO", 7)
    assert val == 7
    assert err is None


def test_parse_int_env_invalid_returns_default_and_error(check_unanswered, monkeypatch):
    monkeypatch.setenv("BAD_INT", "not-a-number")
    val, err = check_unanswered._parse_int_env("BAD_INT", 99)
    assert val == 99
    assert err is not None
    assert "BAD_INT" in err
    assert "not-a-number" in err
    assert "default 99" in err


def test_make_payload_has_all_documented_keys(check_unanswered):
    payload = check_unanswered._make_payload([], [], None, 24, 200, [])
    assert set(payload.keys()) == {
        "unanswered",
        "conversation_since",
        "chat_jid",
        "lookback_hours",
        "context_cap",
        "checked_at",
        "error",
    }


def test_make_payload_success_serializes_error_as_null(check_unanswered):
    payload = check_unanswered._make_payload([], [], None, 24, 200, [])
    roundtripped = json.loads(json.dumps(payload))
    # Confirms `None` reaches the wire as JSON null — the precheck's
    # `if error is None` branch depends on this for the common-case
    # silent path.
    assert roundtripped["error"] is None


def test_make_payload_preserves_lookback_and_context_cap(check_unanswered):
    payload = check_unanswered._make_payload([], [], None, 48, 500, [])
    assert payload["lookback_hours"] == 48
    assert payload["context_cap"] == 500


def test_empty_payload_has_same_shape_as_success(check_unanswered):
    err_payload = check_unanswered._empty_payload("DB locked", 24, 200, [])
    ok_payload = check_unanswered._make_payload([], [], None, 24, 200, [])
    assert set(err_payload.keys()) == set(ok_payload.keys())
    assert err_payload["unanswered"] == []
    assert err_payload["conversation_since"] == []
    assert err_payload["error"] == "DB locked"


def test_merge_env_warnings_no_warnings_returns_primary(check_unanswered):
    assert check_unanswered._merge_env_warnings("DB locked", []) == "DB locked"


def test_merge_env_warnings_no_primary_no_warnings_returns_none(check_unanswered):
    assert check_unanswered._merge_env_warnings(None, []) is None


def test_merge_env_warnings_warnings_only_get_env_warning_prefix(check_unanswered):
    msg = check_unanswered._merge_env_warnings(
        None,
        ["LOOKBACK_HOURS='abc' is not an integer; using default 24"],
    )
    assert msg is not None
    assert msg.startswith("env-warning: ")
    assert "LOOKBACK_HOURS" in msg


def test_merge_env_warnings_primary_plus_warnings_both_surface(check_unanswered):
    msg = check_unanswered._merge_env_warnings(
        "DB locked",
        ["LOOKBACK_HOURS='abc' is not an integer; using default 24"],
    )
    assert msg is not None
    assert "DB locked" in msg
    assert "env-warning: " in msg
    assert "LOOKBACK_HOURS" in msg


def test_merge_env_warnings_multiple_warnings_pipe_joined(check_unanswered):
    msg = check_unanswered._merge_env_warnings(
        None,
        ["bad LOOKBACK_HOURS", "bad CONTEXT_CAP"],
    )
    assert msg is not None
    assert "bad LOOKBACK_HOURS" in msg
    assert "bad CONTEXT_CAP" in msg
    assert " | " in msg


def test_main_missing_chat_jid_exits_1_with_uniform_payload(check_unanswered, capsys, monkeypatch):
    """The early-exit path on missing CHAT_JID still emits the
    canonical JSON shape on stdout, exits non-zero, and writes the
    same reason to stderr — so the precheck's wake-data payload
    surfaces a readable misconfig string instead of an empty one."""
    monkeypatch.setattr(check_unanswered, "CHAT_JID", "")
    rc = check_unanswered.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 1
    assert "NANOCLAW_CHAT_JID" in payload["error"]
    assert payload["unanswered"] == []
    assert payload["conversation_since"] == []
    assert "NANOCLAW_CHAT_JID" in captured.err


def test_main_env_warning_merges_with_primary_error(check_unanswered, capsys, monkeypatch):
    """A bad env var (LOOKBACK_HOURS=abc) AND a missing CHAT_JID
    together exercise _merge_env_warnings inside main(): the payload's
    `error` field carries the primary hard error (CHAT_JID missing)
    AND the env-warning suffix (bad LOOKBACK_HOURS). This is the
    contract `unanswered-precheck.py` reads — it surfaces both to
    operators in a single wake payload."""
    monkeypatch.setattr(check_unanswered, "CHAT_JID", "")
    monkeypatch.setenv("LOOKBACK_HOURS", "abc")
    rc = check_unanswered.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 1
    assert "NANOCLAW_CHAT_JID" in payload["error"]
    assert "env-warning:" in payload["error"]
    assert "LOOKBACK_HOURS" in payload["error"]


def test_main_negative_grace_seconds_clamps_to_zero_with_warning(
    check_unanswered, capsys, monkeypatch
):
    """Negative GRACE_SECONDS clamps to 0 and emits an env-warning.
    Combined with missing CHAT_JID for a deterministic exit path,
    this confirms the clamp-then-warn flow in the integer-validation
    chain."""
    monkeypatch.setattr(check_unanswered, "CHAT_JID", "")
    monkeypatch.setenv("CHECK_UNANSWERED_GRACE_SECONDS", "-5")
    rc = check_unanswered.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 1
    assert "env-warning:" in payload["error"]
    assert "CHECK_UNANSWERED_GRACE_SECONDS" in payload["error"]
    assert "clamping to 0" in payload["error"]
