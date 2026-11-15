# Temporal Awareness Detail

## Proactive timing examples

Calendar and travel context can change between scheduling at 7am and firing at
noon. Consider whether the owner is in-flight, in a meeting, asleep or between
events:

- Hotel checkout before a flight that already departed: the action window closed.
- In-flight: the owner cannot check out of a hotel.
- Traveling to a conference: they may obviously already know they checked out.
- A work alert at 3am local time: timing may be inappropriate.

Judge the situation as a human assistant who knows the owner's full schedule
would, rather than looking for a matching rule.

## Event framing and deadline resolution

Apply the clock and context check to framing events as past, present or future
(“upcoming”, “just happened”, “still time to act”) as well as proactive actions.
For example, resolve `11:00 EDT` to `15:00 UTC` before
`Skill(skill: "now-vs-deadline")`.

## Current-zone contract detail

Consumers retain the unavailable/error handling required by their own workflow.
The accepted record version in the rule is not the database migration number.

Source-authoring verification binds the trusted base manifest to this repository
and reads the declared regular rule; it does not claim an unmerged contract is
installed. See [the contract checks](../../../tests/test_current_tz_contract.py)
and [reader tests](../../../tests/test_read_current_tz.py) for verification.
