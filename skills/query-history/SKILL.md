---
name: query-history
description: Search messages.db for past chat history by keyword and/or sender username. Use when the user references past messages, after context compaction, after a session nuke, or anywhere `rules/context-recovery.md` requires checking the message history before claiming lost context.
---

# Query Message History Skill

Process steps in order. Do not skip ahead.

## Step 1 — Read the Binding Reference

Read the full reference from the installed `jbaruch/nanoclaw-core` provider:

```text
/home/node/.claude/skills/tessl__query-history/references/context-recovery.md
```

Follow its complete directives. Read explicitly, never through an `@` import. If missing or unreadable, stop until repaired. Proceed immediately to Step 2.

## Step 2 — Run the query

Execute the helper in the binding reference's **Required behavior** section. Follow its **Helper execution details** and **Runtime-owned history table** contracts. See `/home/node/.claude/skills/tessl__query-history/references/context-recovery.md`. Proceed immediately to Step 3.

## Step 3 — Act on the result

Apply the reference's output and error handling. Return matched rows in the caller's required format, or proceed silently for a successful empty search. Finish here.
