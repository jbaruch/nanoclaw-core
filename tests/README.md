# Installed core contract acceptance

Run `python -m pytest -q`. `test_rule_references.py` materializes every declared
skill and the startup rules in the host's native layout. It checks all native
pointers and verifies every original contract body against independent byte
counts and SHA-256 digests from [ed9964a](https://github.com/jbaruch/nanoclaw-core/tree/ed9964a/rules).
Only frontmatter is excluded; installed-path and runtime-schema clarifications
follow the unchanged bodies. This covers [#129](https://github.com/jbaruch/nanoclaw-core/issues/129).
`tests/` is excluded by `.tesslignore`; this plugin ships no evals.

After changing a router or reference, verify native-session reads:

1. Run `tessl plugin pack --output /tmp/nanoclaw-core-acceptance.tgz .`.
   Extract outside the checkout. From the packed manifest, copy each declared
   skill to `/home/node/.claude/skills/tessl__<skill>/` and concatenate the
   declared rules into `/home/node/.claude/.tessl/RULES.md`. This mirrors the
   [host materialization contract](https://github.com/jbaruch/nanoclaw/blob/ef8cf4d6837427f8924deda83b7af00c215996fc/src/volume-mounts.ts#L715).
   Verify the packed references match the source byte-for-byte.
2. Start a fresh Claude Code session per row below, with startup rules as context,
   only native `Read` enabled, hooks and external MCP servers disabled. Capture
   tool events with `claude --print --output-format stream-json --verbose`.
   On macOS, translate only the `/home/node` prefix to a temporary root and
   declare that translation in context. Never preload reference text.
3. Ask for a workflow explanation without executing scripts, sending messages or
   querying external systems. Require a successful full native `Read` of the
   named reference before the answer. Partial reads, `@` imports and unsupported
   claims of reading fail acceptance.

| Affected action | Required reference under `/home/node/.claude/skills/` | Required answer |
| --- | --- | --- |
| Explain a long inbound task | `tessl__core-behavior/references/core-behavior.md` | Reaction first; background work; deliver results through `send_message`; no progress narration. |
| Explain a scheduled silent-success wake | `tessl__core-behavior/references/default-silence.md` | No inbound message; no acknowledgement, message, emoji or streamed output for silent success. |
| Explain a Telegram reply | `tessl__core-behavior/references/telegram-protocol.md` | Reply ID for inbound responses; named carve-outs; HTML and correct escaping. |
| Explain verification after scheduling | `tessl__core-behavior/references/ground-truth.md` | Independently inspect authoritative task state; tool success alone is insufficient. |
| Explain a proactive deadline check | `tessl__current-tz/references/temporal-awareness.md` | Host-owned current zone; timezone-aware deadline; helper verdict; no operational fixture clock or handwritten SQL. |
| Explain recovery before claiming lost context | `tessl__query-history/references/context-recovery.md` | Scoped read-only history query; distinguish empty success, runtime failure and usage failure; never replay completed skill blocks. |

4. Repeat with each required reference missing. Require an observed native `Read`
   failure and refusal to proceed with the affected action. Restore the files.
5. Present an irrelevant non-main-chat message in a fresh session. Require zero
   tool calls and zero user-facing output, including internal tags.
   Inspect the transcript for CLI-generated follow-ups: Claude Code can inject
   "Your previous response had no visible output. Please continue and produce a
   user-visible response." An empty initial response followed by that retry does
   not establish end-to-end silence. Verify that boundary in the NanoClaw runner;
   keep the CLI retry separate from the original inbound message.
6. Run the commands in `.github/workflows/test.yml` and `tessl plugin lint .`.
