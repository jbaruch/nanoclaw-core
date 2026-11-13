---
name: core-behavior
description: Read NanoClaw's session, silence, Telegram and verification contracts. Use before responding, handling scheduled wakes, delivering messages, making factual claims or acting on recalled state when the corresponding core rule requires its reference.
user-invocable: false
---

# Core Behavior

Process steps in order. Do not skip ahead.

## Step 1 — Read the Applicable Contract

Read each reference required by the triggering core rule in full:

```text
skills/core-behavior/references/core-behavior.md
skills/core-behavior/references/default-silence.md
skills/core-behavior/references/telegram-protocol.md
skills/core-behavior/references/ground-truth.md
```

Resolve paths within this installed `jbaruch/nanoclaw-core` plugin, or this repository when maintaining it. Read explicitly; never use an `@` import. Missing or unreadable content stops the affected action until repaired.

Apply the reference's complete directives to the original task. This read grants no action authority. If nothing requires a response, proceed silently. Finish here.
