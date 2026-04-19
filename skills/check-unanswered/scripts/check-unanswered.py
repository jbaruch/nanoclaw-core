#!/usr/bin/env python3
"""
Two-phase unanswered message detector.

Phase 1 (deterministic SQL): find user messages that have neither a
threaded bot reply nor a bot reaction. Fast, cheap, no LLM.

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
    "error": str | null,  # `null` on success, short message on failure
  }
Every key is present on both success and error paths so downstream
consumers (unanswered-precheck.py, the skill) can parse uniformly —
check `error` for truthiness to distinguish.

`unanswered` is the Phase-1 candidate set.

`conversation_since` is a chronologically-ordered, deduplicated union
of per-candidate slices: for EACH candidate we collect the first K
messages at or after its (timestamp, id) position, where
K = CONTEXT_CAP / num_candidates (floored at 10). Messages that
appear in multiple candidates' slices collapse via id-dedup.

Coverage caveat — this is an aspirational "each candidate gets its
immediate aftermath" design, not a hard guarantee:
  - The final CONTEXT_CAP truncation drops the earliest slice rows
    when the union exceeds the cap, so a very-early candidate whose
    aftermath sits at the front of the union can lose context. This
    is the right trade: an inline answer is overwhelmingly more
    likely to appear in the LATEST slice (a recent bot message
    acknowledging an older question) than in pre-other-candidate
    clutter, so `[-CONTEXT_CAP:]` keeps the evidence most likely to
    flip Phase 1 candidates to "already addressed."
  - The bulk-fetch path has a row LIMIT scaled to `per_cand * N`;
    if a chat is so active that the last candidate's row sits
    outside that window, we fall back to a targeted SQL query per
    uncovered candidate. Correctness is preserved; performance
    degrades toward the original N+1 only in the pathological
    very-active-chat case.

CONTEXT_CAP defaults to 200.
"""

import bisect
import sqlite3
import json
import sys
import os
from datetime import datetime, timedelta, timezone

DB = os.environ.get('NANOCLAW_DB', '/workspace/store/messages.db')
CHAT_JID = os.environ.get('NANOCLAW_CHAT_JID', '')


def _parse_int_env(name: str, default: int) -> tuple[int, str | None]:
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


LOOKBACK_HOURS, _LB_ERR = _parse_int_env('LOOKBACK_HOURS', 24)
CONTEXT_CAP, _CC_ERR = _parse_int_env('CONTEXT_CAP', 200)
# Clamp non-positive CONTEXT_CAP up to 1 so downstream slicing stays
# sensible (Python's negative-index semantics would otherwise turn
# `context_rows[-0:]` into "keep everything" and `context_rows[-(-5):]`
# into "skip 5 from the front, keep the rest" — both surprising).
# Setting CONTEXT_CAP=0 to silence the context window is rare enough
# that saving one query isn't worth carrying an `if cap == 0` branch
# through the whole flow.
if CONTEXT_CAP < 1:
    _CC_ERR = (
        (_CC_ERR + ' | ' if _CC_ERR else '')
        + f"CONTEXT_CAP={CONTEXT_CAP} is non-positive; clamping to 1"
    )
    CONTEXT_CAP = 1
_env_errors = [e for e in (_LB_ERR, _CC_ERR) if e]
if _env_errors:
    # Non-fatal — defaults are safe and the script still produces
    # useful output. BOTH surface paths matter:
    #   - stderr, so a human tailing the precheck sees it on first tick.
    #   - prepended to `error` in the JSON payload (see `_make_payload`),
    #     so downstream consumers (unanswered-precheck.py → orchestrator
    #     → heartbeat wake) can distinguish "legit no-unanswered run
    #     with a config typo the operator should know about" from
    #     "clean run, all is well" without scraping stderr.
    # Exit stays 0: the script did its job with defaults; crash-looping
    # the precheck on a bad env var is strictly worse than running with
    # sensible defaults and warning loudly.
    sys.stderr.write(" | ".join(_env_errors) + "\n")

# Env-parse warnings get threaded into every emitted payload via a
# closure over `_env_errors`. On the happy path `_make_payload(...,
# None)` still produces error=null, but if an env var was invalid we
# surface "env-warning: ..." so callers can alert without losing the
# actual unanswered set.
_ENV_WARN_PREFIX = "env-warning: "


def _merge_env_warnings(primary: str | None) -> str | None:
    """Combine env-parse warnings with a hard error (if any). Primary
    hard error wins position; env warnings trail. On pure-success
    (primary=None, no env errors) returns None so downstream `if error
    is None` keeps working for the common case."""
    if not _env_errors:
        return primary
    env_msg = _ENV_WARN_PREFIX + " | ".join(_env_errors)
    if primary is None:
        return env_msg
    return f"{primary} ({env_msg})"


def _make_payload(
    unanswered: list,
    conversation_since: list,
    error: str | None,
):
    """Build the single canonical output shape. Used by both the
    happy path (error=None plus no env warnings) and error paths
    (error=short message and/or env-warning surfacing). Every key is
    present in both cases so downstream consumers don't have to
    special-case error JSON."""
    return {
        "unanswered": unanswered,
        "conversation_since": conversation_since,
        "chat_jid": CHAT_JID,
        "lookback_hours": LOOKBACK_HOURS,
        "context_cap": CONTEXT_CAP,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "error": _merge_env_warnings(error),
    }


def _empty_payload(error: str):
    """Shortcut for the error paths: no candidates, no context,
    `error` set."""
    return _make_payload([], [], error)


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
    print(json.dumps(_empty_payload(err)))
    sys.exit(1)

cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime('%Y-%m-%dT%H:%M:%S')

# Single try covering BOTH `sqlite3.connect` and every downstream
# `.execute()` — locked/busy DB on open, locked mid-query, missing or
# renamed table, schema drift, corrupt index, etc. All of them reach the
# same canonical JSON-error + stderr + exit-1 path, so downstream
# consumers never see a raw traceback on stdout (which would break the
# "uniform JSON output shape on error paths" contract and leave
# `unanswered-precheck.py` with a JSON-parse error instead of a
# readable reason string).
#
# We catch `sqlite3.Error` (the base class) rather than just
# `sqlite3.OperationalError` so corruption / integrity errors are
# covered too — the OperationalError-only version shipped earlier and
# turned out to leak tracebacks on corner cases (e.g. missing `messages`
# table if someone pointed the script at a wrong DB path).
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
    """, (CHAT_JID, cutoff)).fetchall()

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
        # Per-candidate context: for EACH candidate we take the first K
        # messages at or after its (timestamp, id) position in the chat's
        # stable sort order. K is CONTEXT_CAP / num_candidates (floored at
        # 10 so even a many-candidate run gives each one some usable
        # context). Dedup by id, sort chronologically with a stable
        # tie-breaker, then hard-cap at CONTEXT_CAP.
        #
        # Previous strategies that failed and why we arrived here:
        #   - Single "first N since earliest" slice: spread-out candidates
        #     had no aftermath visible for the middle/late ones.
        #   - Earliest+latest two-slice union: same problem, just shifted.
        #   - Per-candidate SQL query loop: correctness was right, but N+1
        #     queries hit SQLite N times per precheck — noticeable on busy
        #     chats with many candidates in a 24h lookback.
        #
        # Current approach: ONE bulk fetch from the earliest candidate's
        # position onward, then per-candidate slicing in Python using
        # bisect over a sort-key list. O(N * log M + K_total) work instead
        # of N round-trips to SQLite.
        #
        # Bulk-fetch LIMIT = per_cand * num_candidates: the no-overlap
        # worst case (each candidate's K-row slice is disjoint from every
        # other's) fits in exactly num_candidates * K rows. Overlap can
        # only shrink the union, so this bound is safe; the final
        # CONTEXT_CAP cap below truncates regardless.
        per_cand = max(CONTEXT_CAP // max(len(results), 1), 10)
        earliest = results[0]
        fetch_limit = per_cand * len(results)
        # Lower bound uses lexicographic `(timestamp, id) >= (c_ts, c_id)`,
        # not `timestamp >= c_ts`. With second-precision timestamps a
        # message with the same second but a LOWER id actually occurred
        # BEFORE the earliest candidate in the stable sort order; including
        # it would pollute the window with pre-candidate rows that can't
        # possibly be the inline answer Phase 2 is looking for.
        all_rows = conn.execute(
            """
            SELECT id, sender_name, content, timestamp, is_from_me,
                   is_bot_message, reply_to_message_id
            FROM messages
            WHERE chat_jid = ?
              AND (timestamp > ? OR (timestamp = ? AND id >= ?))
            ORDER BY timestamp ASC, id ASC
            LIMIT ?
            """,
            (
                CHAT_JID,
                earliest["timestamp"],
                earliest["timestamp"],
                earliest["id"],
                fetch_limit,
            ),
        ).fetchall()

        # Build sort-key index once; bisect each candidate's position in
        # O(log M) instead of re-scanning. Key matches the SQL ORDER BY
        # so positions line up exactly.
        row_keys = [(r[3], r[0]) for r in all_rows]
        context_rows_by_id: dict[object, tuple] = {}
        # Candidates whose row wasn't in the bulk fetch (because `fetch_limit`
        # cut off before their position in the chat). Those get a targeted
        # per-candidate query below. Common case is 0 uncovered — the bulk
        # fetch covers everything — so this stays a single-query flow
        # unless the chat is busy enough to blow past fetch_limit.
        uncovered: list[dict] = []
        for cand in results:
            c_key = (cand["timestamp"], cand["id"])
            start = bisect.bisect_left(row_keys, c_key)
            if start >= len(row_keys):
                # Bisect landed past the end of all_rows — the bulk fetch
                # stopped before reaching this candidate's position. Without
                # the fallback below, this candidate would get an empty
                # context slice and Phase 2 would have no evidence to reason
                # from, degrading to blind "true unanswered" for a row that
                # might have been addressed inline.
                uncovered.append(cand)
                continue
            # Slice [start : start+per_cand]; Python handles out-of-range
            # gracefully (empty if start >= len, short if near the end).
            for r in all_rows[start : start + per_cand]:
                context_rows_by_id[r[0]] = r

        # Targeted per-candidate fallback for the uncovered set. At most
        # `len(uncovered)` extra SQL queries — zero in the typical case,
        # strictly less than `len(results)` even in the worst case (any
        # candidate whose row WAS in all_rows was already handled above).
        for cand in uncovered:
            rows = conn.execute(
                """
                SELECT id, sender_name, content, timestamp, is_from_me,
                       is_bot_message, reply_to_message_id
                FROM messages
                WHERE chat_jid = ?
                  AND (timestamp > ? OR (timestamp = ? AND id >= ?))
                ORDER BY timestamp ASC, id ASC
                LIMIT ?
                """,
                (
                    CHAT_JID,
                    cand["timestamp"],
                    cand["timestamp"],
                    cand["id"],
                    per_cand,
                ),
            ).fetchall()
            for r in rows:
                context_rows_by_id[r[0]] = r

        context_rows = sorted(
            context_rows_by_id.values(), key=lambda r: (r[3], r[0])
        )
        # Final hard cap at CONTEXT_CAP: honors the operator-configured
        # upper bound regardless of how the per-candidate slices unioned.
        # Keep the LATEST rows on tie (slicing by `[-cap:]`) — newer
        # evidence is more likely to contain an inline answer Phase 1's
        # SQL filter missed.
        if len(context_rows) > CONTEXT_CAP:
            context_rows = context_rows[-CONTEXT_CAP:]
        conversation_since = [
            {
                "id": r[0],
                "sender_name": r[1],
                "content": r[2],
                "timestamp": r[3],
                # A message is "from the bot" if either flag is set —
                # older rows set `is_from_me=1` for the main-bot identity
                # while pool-bot sends set `is_bot_message=1`. Unified
                # here so the skill doesn't have to know which column
                # applies.
                "from_bot": bool(r[4]) or bool(r[5]),
                "reply_to_id": r[6],
            }
            for r in context_rows
        ]
    else:
        conversation_since = []
except sqlite3.Error as e:
    # Any sqlite error — open failure OR post-open query/schema errors.
    # Emit the canonical error JSON on stdout, a short human-readable
    # reason on stderr (the precheck wrapper uses `result.stderr[:500]`
    # for its wake-data error field), and exit non-zero so the precheck
    # treats this as "wake the agent" rather than "clean empty result."
    # Distinguishing open vs query failure in the message helps operators
    # triage (config/path issue vs runtime DB issue).
    phase = "open" if conn is None else "query"
    err = f"DB {phase} failed: {e}"
    sys.stderr.write(err + "\n")
    print(json.dumps(_empty_payload(err)))
    if conn is not None:
        # `conn.close()` on a successfully-opened connection rarely
        # fails, but if it does (underlying fd already gone, etc.)
        # surface the secondary error on stderr so it's visible —
        # without shadowing the primary cause above. Silencing would
        # violate the no-error-suppression rule.
        try:
            conn.close()
        except sqlite3.Error as close_err:
            sys.stderr.write(f"(secondary: close failed: {close_err})\n")
    sys.exit(1)

conn.close()

print(json.dumps(_make_payload(results, conversation_since, None)))
