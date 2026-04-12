# Progress Updates for Long Tasks

When launching a background agent for a task that may take more than 30 seconds, include this instruction in the agent prompt:

> If your work takes more than 30 seconds, send a brief progress update via `mcp__nanoclaw__send_message` before delivering the final result. Keep it short and contextual — what you're doing right now, not a status report.

## Examples of good progress updates

- "Ищу в почте за последние 3 дня..."
- "Нашёл 4 письма, анализирую..."
- "Checking 3 GitHub repos..."
- "Found the issue, writing fix..."

## Examples of bad progress updates

- "Still working on your request." (generic, no context)
- "Processing step 2 of 5..." (robotic)
- "I'm currently in the process of..." (LLM-speak)

## Rules

- The initial emoji reaction remains the first acknowledgement — progress updates come AFTER, only if work is lengthy.
- One update is usually enough. Two max for very long tasks. Don't spam.
- Match the language of the original message.
- If the task finishes quickly (<30s), no update needed — just deliver the result.
- Progress updates use `send_message` with the same `reply_to` as the final result.
