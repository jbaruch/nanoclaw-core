---
name: check-unanswered
description: "Finds user messages that lack a threaded bot reply or reaction, then reasons over the conversation since each candidate to decide whether the bot already addressed it inline. Reacts with 👍 to mark inline-addressed candidates as processed; sends a threaded reply only for truly-unanswered ones. Use when checking for missed messages, unanswered messages, dropped replies, or messages without responses — during context recovery or heartbeat checks."
---

# Check Unanswered Messages

The deterministic script finds candidates — user messages without a threaded bot reply or bot reaction. But sometimes the bot answers a question inline, in normal conversational flow, without threading or reacting. Those messages look unanswered to SQL but aren't. **Phase 2 closes the gap with LLM reasoning.**

## Step 1: Run the script

```bash
python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/check-unanswered.py
```

Output JSON fields:
- `unanswered`: Phase-1 candidates — user messages matching the SQL filter (no bot reply, no bot reaction).
- `conversation_since`: every chat message from the earliest candidate's timestamp to now, chronologically, capped at 200. Each entry has `{id, sender_name, content, timestamp, from_bot, reply_to_id}`.
- `chat_jid`, `lookback_hours`, `context_cap`, `checked_at`: metadata.

If `unanswered` is empty, stop — nothing to report.

## Step 2: Per-candidate Phase 2 reasoning

For **each** candidate in `unanswered`, scan `conversation_since` for bot messages (`from_bot: true`) sent AFTER the candidate's `timestamp`. Ask:

> Did any of those bot messages substantively address this candidate's content — answer its question, acknowledge its request, follow up on its topic — even though they weren't threaded via `reply_to_id`?

Decide **YES** or **NO**.

**Guidance:**
- Be conservative. If a bot message could plausibly be a response (topic match, question answered, request acknowledged), treat it as YES.
- An unrelated bot message (TripIt notification, heartbeat status, a reply to a DIFFERENT user that happened in the same window) is not an answer — treat as NO.
- If the candidate was sent right before a completely unrelated user message from the same person, and the bot's subsequent messages addressed the newer message, the older candidate is likely still unanswered — treat as NO.
- When genuinely uncertain, prefer **NO**. A duplicate response is a minor annoyance; a dropped question is worse.

## Step 3: Act on the decision

**If YES (addressed inline):** react 👍 to the candidate so the next heartbeat's SQL excludes it.
```
mcp__nanoclaw__react_to_message(messageId: <candidate.id>, emoji: "👍")
```
Do NOT also send a threaded reply — that would duplicate the answer.

**If NO (truly unanswered):** send a threaded reply that addresses the original.
```
mcp__nanoclaw__send_message(text: <response>, reply_to: <candidate.id>)
```
The `reply_to` threading is what makes the next heartbeat's SQL exclude it (a bot message with `reply_to_message_id` pointing to the candidate counts as "handled"). No reaction needed in this branch.

## Step 4: Verify

For every candidate processed in Step 3, confirm the corresponding reaction OR threaded reply landed. If an action failed, retry before marking the heartbeat complete.

## Requirements

`NANOCLAW_CHAT_JID` must be set in the environment. The script returns an error JSON (not a crash) if missing.

## Pre-check for scheduled tasks

For group heartbeat tasks that only check unanswered messages, the pre-check script gates the LLM so the agent doesn't spawn when nothing changed:

```bash
python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/unanswered-precheck.py
```

It runs `check-unanswered.py` internally, compares the candidate ID set against the last seen set (persisted under `/home/node/.claude/nanoclaw-state/unanswered-seen.json`), and outputs `{"wakeAgent": false}` if the set hasn't changed. Use as the `script` field on any group's heartbeat `schedule_task`.

When the agent IS woken, it re-runs `check-unanswered.py` itself (Step 1 above) to get the full Phase-2-ready output including `conversation_since`.
