---
name: check-unanswered
description: "Finds user messages that lack a threaded bot reply or reaction, then reasons over the conversation since each candidate to decide whether the bot already addressed it inline. Reacts with 👍 to mark inline-addressed candidates as processed; sends a threaded reply only for truly-unanswered ones. Use when checking for missed messages, unanswered messages, dropped replies, or messages without responses — during context recovery or heartbeat checks."
---

# Check Unanswered Messages

Two-phase process: Phase 1 (SQL) finds candidates — user messages without a threaded bot reply or reaction. Phase 2 (LLM reasoning) judges whether any of those were actually answered inline in normal conversational flow, just without threading or a reaction.

## Pre-check (scheduled/heartbeat tasks only)

For group heartbeat tasks that only check unanswered messages, a pre-check script gates the LLM so the agent doesn't spawn when nothing changed:

```bash
python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/unanswered-precheck.py
```

Outputs `{"wakeAgent": false}` if the candidate ID set is unchanged since the last run. Use as the `script` field on any group's heartbeat `schedule_task`. When the agent IS woken, proceed to Step 1 to get the full Phase-2-ready output.

---

## Step 1: Run the script

```bash
python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/check-unanswered.py
```

Output JSON fields:
- `unanswered`: Phase-1 candidates — user messages matching the SQL filter (no bot reply, no bot reaction).
- `conversation_since`: chat messages chronologically around the candidates, so Phase 2 can judge inline answers. Each entry: `{id, sender_name, content, timestamp, from_bot, reply_to_id}`. Default `context_cap`: 200.
- `chat_jid`, `lookback_hours`, `context_cap`, `checked_at`: metadata.
- `error` (only on failure paths): short string describing what went wrong (missing `NANOCLAW_CHAT_JID`, DB open failure, etc.). The script also exits non-zero in this case, so the precheck wrapper surfaces the failure rather than treating it as "no unanswered messages."

**Stop condition:** only stop if `unanswered` is empty AND no `error` is present. If `error` is set, report it — the heartbeat is mis-wired or the DB is sick.

**Requirements:** `NANOCLAW_CHAT_JID` must be set in the environment. The script returns an error JSON (not a crash) if missing.

## Step 2: Per-candidate Phase 2 reasoning

For **each** candidate in `unanswered`, scan `conversation_since` for bot messages (`from_bot: true`) sent AFTER the candidate's `timestamp`. Ask:

> Did any of those bot messages substantively address this candidate's content — answer its question, acknowledge its request, follow up on its topic — even though they weren't threaded via `reply_to_id`?

Decide **YES** or **NO**.

**A single clear bar for YES, everything else is NO.**

Say **YES** only when you can point to a specific bot message that clearly addresses this candidate's content. Name the message ID (or the gist) to yourself as a sanity check; if you can't, it's not a match.

**Common NO cases:**
- Unrelated bot message (TripIt notification, heartbeat status, a reply to a different user).
- Bot's subsequent messages addressed a newer user message, not this candidate.
- Vague overlap only: "topic overlaps" or "could plausibly be a response" is not enough.

Bias: prefer false-positive replies over dropped questions.

## Step 3: Act on the decision

**If YES (addressed inline):** react 👍 to the candidate so the next heartbeat's SQL excludes it.
```
mcp__nanoclaw__react_to_message(messageId: <candidate.id>, emoji: "👍")
```
Do NOT also send a threaded reply.

**If NO (truly unanswered):** send a threaded reply that addresses the original.
```
mcp__nanoclaw__send_message(text: <response>, reply_to: <candidate.id>)
```
No reaction needed in this branch.

## Step 4: Verify

For every candidate processed in Step 3, confirm the corresponding reaction OR threaded reply landed. If an action failed, retry before marking the heartbeat complete.
