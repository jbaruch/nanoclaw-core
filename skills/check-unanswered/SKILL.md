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
- `conversation_since`: chat messages chronologically around the candidates, so Phase 2 can judge inline answers. Internally, this is the deduped union of `context_cap/2` messages from the earliest candidate and `context_cap/2` from the latest — the typical close-together case collapses to one window, and the spread-out case keeps each candidate's immediate aftermath visible. Each entry: `{id, sender_name, content, timestamp, from_bot, reply_to_id}`. Default `context_cap`: 200.
- `chat_jid`, `lookback_hours`, `context_cap`, `checked_at`: metadata.
- `error` (only on failure paths): short string describing what went wrong (missing `NANOCLAW_CHAT_JID`, DB open failure, etc.). The script also exits non-zero in this case, so the precheck wrapper surfaces the failure rather than treating it as "no unanswered messages."

**Stop condition:** only stop if `unanswered` is empty AND no `error` is present. If `error` is set, report it (don't silently treat as "nothing to do") — the heartbeat is mis-wired or the DB is sick.

## Step 2: Per-candidate Phase 2 reasoning

For **each** candidate in `unanswered`, scan `conversation_since` for bot messages (`from_bot: true`) sent AFTER the candidate's `timestamp`. Ask:

> Did any of those bot messages substantively address this candidate's content — answer its question, acknowledge its request, follow up on its topic — even though they weren't threaded via `reply_to_id`?

Decide **YES** or **NO**.

**Policy: a single clear bar for YES, everything else is NO.**

Say **YES** only when you can point to a specific bot message in `conversation_since` that clearly addresses this candidate's content — answering its question, acknowledging its request, or directly engaging with its topic. Name the message ID (or the gist) to yourself as a sanity check; if you can't, it's not a match.

Everything else — including "could plausibly be a response," "topic overlaps vaguely," "bot said something after" — is **NO**.

Common NO cases:
- An unrelated bot message (TripIt notification, heartbeat status, a reply to a DIFFERENT user in the same window).
- The candidate was followed by a different user message, and the bot's subsequent messages addressed the newer message rather than this candidate.
- Bot replied to an adjacent topic but not the specific question in the candidate.

Rationale: a duplicate response is a mild annoyance ("I already answered that" → easy to dismiss); a dropped question is worse (user waits, disengages, loses trust in the heartbeat). Bias toward fresh replies.

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
