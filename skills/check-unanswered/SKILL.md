---
name: check-unanswered
description: "Finds user messages that lack a threaded bot reply or reaction, then reasons over the conversation since each candidate to decide whether the bot already addressed it inline. Reacts with 👍 to mark inline-addressed candidates as processed; sends a threaded reply only for truly-unanswered ones. Use when checking for missed messages, unanswered messages, dropped replies, or messages without responses — during context recovery or heartbeat checks."
---

# Check Unanswered Messages

Two-phase process: Phase 1 (SQL) finds candidates — user messages without a threaded bot reply or reaction. Phase 2 (LLM reasoning) judges whether any were actually answered inline in normal conversational flow, without threading or a reaction.

## Step 1: Run the script

```bash
python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/check-unanswered.py
```

Output JSON fields:
- `unanswered`: Phase-1 candidates — user messages matching the SQL filter (no bot reply, no bot reaction).
- `conversation_since`: chat messages chronologically around the candidates for Phase 2 judgment. Each entry: `{id, sender_name, content, timestamp, from_bot, reply_to_id}`. Default `context_cap`: 200.
- `chat_jid`, `lookback_hours`, `context_cap`, `checked_at`: metadata.
- `error`: `null` on clean success; short string on failure. Prefixed `env-warning:` for non-fatal config hints; hard failures (missing `NANOCLAW_CHAT_JID`, DB access failure) also exit non-zero so the precheck wrapper surfaces them.

**Stop condition:** stop silently only if `unanswered` is empty AND `error` is `null`. If `error` is non-null, report it.

## Step 2: Per-candidate Phase 2 reasoning

For **each** candidate in `unanswered`, scan `conversation_since` for bot messages (`from_bot: true`) sent AFTER the candidate's `timestamp`. Ask:

> Did any of those bot messages substantively address this candidate's content — answer its question, acknowledge its request, follow up on its topic — even without a `reply_to_id` thread?

Decide **YES** or **NO**. Say **YES** only when you can point to a specific bot message that clearly addresses the candidate. Note the message ID or gist as a sanity check; if you can't identify one, it's NO.

**Common NO cases:**
- Unrelated bot message (TripIt notification, heartbeat status, reply to a different user).
- Bot's subsequent messages addressed a newer user message, not this candidate.
- Vague overlap only — "topic overlaps" or "could plausibly be a response" is not enough.

Bias: prefer false-positive replies over dropped questions.

## Step 3: Act on the decision

**If YES (addressed inline):** react 👍 to exclude the candidate from the next heartbeat's SQL.
```
mcp__nanoclaw__react_to_message(messageId: <candidate.id>, emoji: "👍")
```
Do NOT also send a threaded reply — that would duplicate the answer.

**If NO (truly unanswered):** send a threaded reply addressing the original.
```
mcp__nanoclaw__send_message(text: <response>, reply_to: <candidate.id>)
```
The `reply_to` threading excludes it from the next SQL. No reaction needed in this branch.

## Step 4: Verify

For every candidate processed in Step 3, confirm the reaction or threaded reply landed. Retry any failed action before marking the heartbeat complete.

## Requirements

`NANOCLAW_CHAT_JID` must be set in the environment. The script returns an error JSON (not a crash) if missing.

## Pre-check for scheduled tasks

For group heartbeat tasks that only check unanswered messages, the pre-check script gates the LLM so the agent doesn't spawn when nothing changed:

```bash
python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/unanswered-precheck.py
```

It runs `check-unanswered.py` internally, compares the candidate ID set against the last seen set (persisted under `/home/node/.claude/nanoclaw-state/unanswered-seen.json`), and outputs `{"wakeAgent": false}` if the set hasn't changed. Use as the `script` field on any group's heartbeat `schedule_task`.

When the agent IS woken, it re-runs `check-unanswered.py` itself (Step 1 above) to get the full Phase-2-ready output including `conversation_since`.
