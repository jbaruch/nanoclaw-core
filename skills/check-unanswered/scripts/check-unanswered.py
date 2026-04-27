#!/usr/bin/env python3
"""
Two-phase unanswered message detector.

Phase 1 (deterministic SQL): find user messages that have neither a
threaded bot reply nor a bot reaction. Fast, cheap, no LLM. A grace
window (default 60s, env `CHECK_UNANSWERED_GRACE_SECONDS`) excludes
very-recent messages so an in-flight bot reply has time to commit
before the message becomes a Phase-1 candidate — closes the
heartbeat-vs-reply race documented in #18.

Phase 2 (LLM-assisted, in the skill): for each candidate, reason over
the conversation between that message and now to decide whether the
bot already addressed it inline (without using reply_to_message_id or
reacting). Phase 2 lives in the skill workflow, not in this script —
scripts can't do "did this bot message substantively respond to that
user message" reliably, and the phrasing of the question is exactly
what LLMs are for.

Output shape:
  {
    "unanswered": [ {id, sender_name, content, timestamp}, ... ],
    "conversation_since": [ {id, sender_name, content, timestamp,
                             from_bot, reply_to_id}, ... ],
    "chat_jid": str,
    "lookback_hours": int,
    "context_cap": int,
    "checked_at": ISO-8601,
    "error": str | null,  # `null` on clean success; short message on
                          # hard failure OR env-var warning (prefixed
                          # with `env-warning:` when it's a warning).
  }
Every key is present on both success and error paths so downstream
consumers (unanswered-precheck.py, the skill) can parse uniformly.
Interpret `error` as three states, not two:
  - `null`                    → clean success, nothing to report.
  - starts with `env-warning:` → non-fatal config issue; script still
                                 produced a useful result. Surface to
                                 operator (logs/wake payload) but don't
                                 treat as failure.
  - anything else             → hard failure; script also exits
                                 non-zero, so downstream consumers
                                 keying on returncode already wake.

`unanswered` is the Phase-1 candidate set.
`conversation_since` is a chronologically-ordered, deduplicated union
of per-candidate slices: for EACH candidate we fetch the first K
messages starting at its timestamp, where K = CONTEXT_CAP /
num_candidates (floored at 10). Messages that appear in multiple
candidates' slices collapse via id-dedup. This guarantees every
candidate — including middle ones in a spread-out set — has its
immediate aftermath in-window, which is where an inline bot answer
would land. A final hard cap at `CONTEXT_CAP` keeps
`len(conversation_since) <= context_cap` as a firm invariant; if the
union exceeds the cap (very active chat + many candidates), we keep
the LATEST rows, because newer evidence is more likely to contain
answers Phase 1's filter missed. CONTEXT_CAP defaults to 200.

Exit codes:
  0 — success (clean payload on stdout, env-var warnings (if any)
      surfaced via `error: "env-warning: ..."` field).
  1 — runtime failure: required env var missing, DB access failure,
      or any `sqlite3.Error` during connect/query. Diagnostic on
      stderr, empty-payload JSON on stdout, exits non-zero so the
      precheck wakes the operator.
  2 — reserved for usage errors. Not currently emitted (the script
      takes no positional args), but reserved so the docstring/code
      contract stays predictable for future flag additions.
"""

import sqlite3
import json
import sys
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

DB = os.environ.get('NANOCLAW_DB', '/workspace/store/messages.db')
CHAT_JID = os.environ.get('NANOCLAW_CHAT_JID', '')
_ENV_WARN_PREFIX = "env-warning: "


def _parse_int_env(name: str, default: int) -> Tuple[int, Optional[str]]:
    """Parse an integer env var, returning (value, error). On invalid
    input we fall back to `default` AND surface the original input in
    the error string so the caller can emit it to stderr — without
    this, a misconfigured `LOOKBACK_HOURS=abc` would crash the script
    with a traceback on stdout, breaking the "uniform JSON output
    shape on error paths" guarantee."""
    raw = os.environ.get(name)
    if raw is None or raw == '':
        return default, None
    try:
        return int(raw), None
    except ValueError:
        return default, f"{name}={raw!r} is not an integer; using default {default}"


def _merge_env_warnings(primary: Optional[str], env_errors: List[str]) -> Optional[str]:
    """Thread any env-parse warnings into the payload's `error` field
    alongside a hard error (if any). Primary hard error wins position;
    env warnings trail. On pure-success (primary=None, no env errors)
    returns None so downstream `if error is None` keeps working for
    the common case — the precheck's stop condition shouldn't change
    semantics just because an env var is slightly off."""
    if not env_errors:
        return primary
    env_msg = _ENV_WARN_PREFIX + " | ".join(env_errors)
    if primary is None:
        return env_msg
    return f"{primary} ({env_msg})"


def _make_payload(
    unanswered: list,
    conversation_since: list,
    error: Optional[str],
    lookback_hours: int,
    context_cap: int,
    env_errors: List[str],
):
    """Build the single canonical output shape. Used by both the happy
    path (error=None, no env warnings → `error` serializes as `null`)
    and error paths (error=short message and/or env-warning surfacing).
    Every key is present in both cases so downstream consumers don't
    have to special-case error JSON."""
    return {
        "unanswered": unanswered,
        "conversation_since": conversation_since,
        "chat_jid": CHAT_JID,
        "lookback_hours": lookback_hours,
        "context_cap": context_cap,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "error": _merge_env_warnings(error, env_errors),
    }


def _empty_payload(
    error: str,
    lookback_hours: int,
    context_cap: int,
    env_errors: List[str],
):
    """Shortcut for the error paths: no candidates, no context,
    `error` set."""
    return _make_payload([], [], error, lookback_hours, context_cap, env_errors)


def main() -> int:
    lookback_hours, lb_err = _parse_int_env('LOOKBACK_HOURS', 24)
    context_cap, cc_err = _parse_int_env('CONTEXT_CAP', 200)
    # Grace window — exclude messages younger than `grace_seconds` from
    # the candidate set. Closes the heartbeat-vs-bot-reply race
    # documented in #18: when the bot is mid-reply (or about to react)
    # and the heartbeat lands in the window before the threaded reply /
    # reaction commits, Phase 1's SQL would otherwise flag the message
    # as unanswered, the agent wakes, and a duplicate reply ships. The
    # grace window lets the in-flight reply land before the message
    # becomes eligible. Mirrors the upstream `SWEEP_INTERVAL_MS=60000`
    # behavior in qwibitai/nanoclaw `src/host-sweep.ts`.
    grace_seconds, gs_err = _parse_int_env('CHECK_UNANSWERED_GRACE_SECONDS', 60)
    if grace_seconds < 0:
        gs_err = (
            (gs_err + ' | ' if gs_err else '')
            + f"CHECK_UNANSWERED_GRACE_SECONDS={grace_seconds} is negative; clamping to 0"
        )
        grace_seconds = 0
    # Clamp non-positive CONTEXT_CAP up to 1 so downstream slicing stays
    # sensible (Python's negative-index semantics would otherwise turn
    # `context_rows[-0:]` into "keep everything" and `context_rows[-(-5):]`
    # into "skip 5 from the front, keep the rest" — both surprising).
    # Setting CONTEXT_CAP=0 to silence the context window is rare enough
    # that saving one query isn't worth carrying an `if cap == 0` branch
    # through the whole flow.
    if context_cap < 1:
        cc_err = (
            (cc_err + ' | ' if cc_err else '')
            + f"CONTEXT_CAP={context_cap} is non-positive; clamping to 1"
        )
        context_cap = 1
    env_errors = [e for e in (lb_err, cc_err, gs_err) if e]
    if env_errors:
        # Non-fatal — defaults are safe and the script still produces
        # useful output. Two surface paths, each with a different audience:
        #   - stderr, for operators running this script directly (container
        #     shell, ad-hoc debugging). NOT the channel for scheduled runs:
        #     `unanswered-precheck.py` uses capture_output=True and only
        #     forwards stderr on non-zero exit, so the scheduler never sees
        #     stderr from a successful run.
        #   - JSON payload `error` field with an `env-warning:` prefix (see
        #     `_merge_env_warnings` / `_make_payload`). THIS is the channel
        #     scheduled consumers read; the precheck propagates it into its
        #     own output so operators see config issues in the wake payload
        #     rather than having to tail container logs.
        # Exit stays 0: the script did its job with defaults; crash-looping
        # the precheck on a bad env var is strictly worse than running with
        # sensible defaults and warning loudly.
        sys.stderr.write(" | ".join(env_errors) + "\n")

    if not CHAT_JID:
        # NANOCLAW_CHAT_JID must be set. Without it, the script cannot
        # determine which group to check. The previous fallback (most
        # recent bot message) was removed because it could select the
        # wrong group when the DB contains messages from multiple chats.
        #
        # Exit non-zero so callers that check the process exit code (e.g.
        # unanswered-precheck.py's `if result.returncode != 0: wake agent`)
        # surface the misconfig instead of treating it as "no unanswered
        # messages, nothing to do." Also emit the same message to stderr —
        # the precheck wraps stderr into its wake-data payload, so operators
        # see the actual reason for the wake instead of an opaque empty
        # string.
        err = "NANOCLAW_CHAT_JID not set — required env var."
        sys.stderr.write(err + "\n")
        print(json.dumps(_empty_payload(err, lookback_hours, context_cap, env_errors)))
        return 1

    now_utc = datetime.now(timezone.utc)
    cutoff = (now_utc - timedelta(hours=lookback_hours)).strftime('%Y-%m-%dT%H:%M:%S')
    grace_cutoff = (now_utc - timedelta(seconds=grace_seconds)).strftime('%Y-%m-%dT%H:%M:%S')

    # Single try/finally covering BOTH `sqlite3.connect` and every
    # downstream `.execute()` — locked/busy DB on open, locked mid-query,
    # missing or renamed table, schema drift, corrupt index, etc. All of
    # them reach the same canonical JSON-error + stderr + exit-1 path, so
    # downstream consumers never see a raw traceback on stdout (which
    # would break the "uniform JSON output shape on error paths" contract
    # and leave `unanswered-precheck.py` with a JSON-parse error instead
    # of a readable reason string).
    #
    # We catch `sqlite3.Error` (the base class) rather than just
    # `sqlite3.OperationalError` so corruption / integrity errors are
    # covered too — the narrower version leaks tracebacks on corner cases
    # (e.g. `DatabaseError` when the `messages` table is missing because
    # someone pointed the script at the wrong DB path).
    conn = None
    try:
        conn = sqlite3.connect(DB, timeout=5)

        # Phase 1: find user messages with no bot reply AND no bot reaction.
        # A message is "handled" if either:
        #   1. A bot message exists with reply_to_message_id pointing to it, OR
        #   2. The bot already reacted to it (previous heartbeat marked it
        #      addressed inline via Phase 2 reasoning).
        #
        # The "bot message" predicate accepts EITHER flag:
        #   - `r.is_from_me = 1` covers main-bot sends (the orchestrator's
        #     primary Telegram identity).
        #   - `r.is_bot_message = 1` covers pool-bot sends (agent-swarm bots
        #     operating under a per-sender identity; written by the
        #     orchestrator's `sendPoolMessage` code path).
        # A narrower check that only matched `is_from_me = 1` missed pool-bot
        # threaded replies, so the main-bot + pool-bot mix would resurface
        # already-answered messages as candidates.
        unanswered = conn.execute("""
            SELECT m.id, m.sender_name, m.content, m.timestamp
            FROM messages m
            WHERE m.chat_jid = ?
              AND m.is_from_me = 0
              AND m.is_bot_message = 0
              AND m.timestamp > ?
              -- Grace window per #18: skip messages younger than
              -- CHECK_UNANSWERED_GRACE_SECONDS so an in-flight reply
              -- has time to commit before the message becomes a
              -- candidate. Closes the heartbeat-vs-reply race that
              -- caused duplicate-reply incidents.
              AND m.timestamp < ?
              AND NOT EXISTS (
                SELECT 1 FROM messages r
                WHERE r.chat_jid = m.chat_jid
                  AND (r.is_from_me = 1 OR r.is_bot_message = 1)
                  AND r.reply_to_message_id = m.id
              )
              AND NOT EXISTS (
                SELECT 1 FROM reactions rc
                WHERE rc.message_id = m.id
                  AND rc.message_chat_jid = m.chat_jid
                  AND rc.reactor_jid = 'bot@telegram'
              )
            -- id is the tie-break: SQLite timestamps are second-precision in
            -- some paths, and two messages in the same second would otherwise
            -- sort non-deterministically. Downstream code picks results[0]
            -- and results[-1] as "earliest/latest candidate" for context-
            -- window planning; a stable order keeps those picks reproducible.
            ORDER BY m.timestamp ASC, m.id ASC
        """, (CHAT_JID, cutoff, grace_cutoff)).fetchall()

        results = [
            {"id": msg_id, "sender_name": sender, "content": content, "timestamp": ts}
            for msg_id, sender, content, ts in unanswered
        ]

        # Phase 2 context: a bounded window of chat messages around the
        # candidates (see per-candidate slicing below). The skill reads this
        # to decide per-candidate "did a subsequent bot message address this
        # inline?" — without the context, there's no reasoning possible and
        # the skill degrades to blind reply-to-every-candidate, which is
        # exactly the duplicate-answer bug this script exists to avoid.
        if results:
            # Per-candidate context: for EACH candidate we fetch the first K
            # messages from its timestamp onward. K is CONTEXT_CAP /
            # num_candidates (floored at 10 so even a many-candidate run gives
            # each one some usable context). Dedup by id, sort chronologically
            # with a stable tie-breaker, then hard-cap at CONTEXT_CAP.
            #
            # Previous strategies (single "first N since earliest" slice;
            # two-slice earliest+latest union) could leave MIDDLE candidates
            # in a spread-out set with no immediate-aftermath context, which
            # is exactly the evidence Phase 2 reasoning needs. Per-candidate
            # slicing costs num_candidates queries but guarantees every
            # candidate has at least K rows after it in the window.
            per_cand = max(context_cap // max(len(results), 1), 10)
            context_rows_by_id: dict = {}
            for cand in results:
                rows = conn.execute(
                    """
                    SELECT id, sender_name, content, timestamp, is_from_me, is_bot_message, reply_to_message_id
                    FROM messages
                    WHERE chat_jid = ?
                      AND timestamp >= ?
                    -- Stable tie-break by id so the LIMIT window is
                    -- deterministic when timestamps tie at second precision.
                    -- Without it, which rows make it into the per-candidate
                    -- slice under ties is undefined and can intermittently
                    -- drop the bot message that addressed the candidate.
                    ORDER BY timestamp ASC, id ASC
                    LIMIT ?
                    """,
                    (CHAT_JID, cand["timestamp"], per_cand),
                ).fetchall()
                for r in rows:
                    context_rows_by_id[r[0]] = r
            context_rows = sorted(
                context_rows_by_id.values(), key=lambda r: (r[3], r[0])
            )
            # Final hard cap at context_cap: honors the operator-configured
            # upper bound regardless of how the per-candidate slices unioned.
            # Keep the LATEST rows on tie (slicing by `[-cap:]`) — newer
            # evidence is more likely to contain an inline answer Phase 1's
            # SQL filter missed.
            if len(context_rows) > context_cap:
                context_rows = context_rows[-context_cap:]
            conversation_since = [
                {
                    "id": r[0],
                    "sender_name": r[1],
                    "content": r[2],
                    "timestamp": r[3],
                    # A message is "from the bot" if either flag is set — older
                    # rows set `is_from_me=1` for the main-bot identity while
                    # pool-bot sends set `is_bot_message=1`. Unified here so the
                    # skill doesn't have to know which column applies.
                    "from_bot": bool(r[4]) or bool(r[5]),
                    "reply_to_id": r[6],
                }
                for r in context_rows
            ]
        else:
            conversation_since = []
    except sqlite3.Error as e:
        # DB access failure is a hard problem worth waking someone for,
        # not a silent "zero orphans" answer.
        err = f"DB access failed: {e}"
        sys.stderr.write(err + "\n")
        print(json.dumps(_empty_payload(err, lookback_hours, context_cap, env_errors)))
        return 1
    finally:
        if conn is not None:
            conn.close()

    print(json.dumps(_make_payload(results, conversation_since, None, lookback_hours, context_cap, env_errors)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
