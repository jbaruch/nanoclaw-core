# Verification Context

LLMs synthesize plausible answers from prior context, which can produce
confident wrong reports. Memory of what should be installed is not evidence
of what is installed. Recalled file paths, task state, deploy freezes and config
flags can all go stale.

Tool-call success means the tool ran; it does not establish that the outcome
matches the intent.
