---
name: flowlines-release-check
description: Check whether a release of an agent changed its outcomes in Flowlines - compare sessions, success rates, intents, cost, and signals before and after a deploy over the Flowlines MCP server. Use when the user asks whether a deploy, prompt change, or new version regressed or improved anything, or wants a go/no-go after shipping.
---

# Flowlines release check

Answer "did the last release change anything?" with numbers that have the right denominators, evidence from real sessions, and an honest statement of what cannot be known yet.

## Conventions for every Flowlines tool call

- Every tool takes `reason` and `user_intent`. Keep `user_intent` identical across the conversation, for example "Check whether the 2026-09-01 release of the support agent regressed outcomes".
- Start with `get_workspace` once, then `get_context` for the namespace. Read pinned notes: a known evaluator artifact or ingestion gap changes how a comparison reads.
- Quote the minimum from sessions and mask identifiers. Prefer aggregates.
- End with `report_outcome` as the last tool call.

## Inputs

1. The agent. `list_agents` shows the names Flowlines observes; use the exact name in filters.
2. The release boundary as an ISO 8601 timestamp. Take it from the user, the deploy log, or the release list in the Flowlines app under Versions. Flowlines records a release either from a reported agent version or from a detected prompt change; the app's release receipt shows which.
3. The comparison window. Default to the same number of days on each side of the boundary, at least 3 and at most 14, so both sides have comparable traffic. Say when the after-window is still short.

## Steps

1. `get_changes_since` with `since` set to the release boundary. This gives the after-side activity, outcomes, signals, and pinned notes in one call.
2. Build the two windows from day buckets. `aggregate_sessions` only accepts trailing ranges that end now (`24h`, `7d`, `30d`, `90d`, `all`), so any range you pick contains post-release activity. Query the smallest range that covers both windows with `group_by: ["day"]` and metrics `session_count`, `user_count`, `success_count`, `failure_count`, `total_cost_usd`, `unanalyzed_count`, filtered by `agent_name`. Assign each day bucket to the before or after window yourself. The deployment day is mixed: exclude it from both windows unless the boundary falls at the start of the day, and say which choice you made. Day buckets cannot represent a boundary inside a day exactly; say so, and if that precision matters use `list_sessions` with `from` and `to` around the boundary for counts on that day only.
3. Compute rates from the summed counts, never by averaging per-day or per-group rates: success rate for a window is the sum of `success_count` divided by the sum of `success_count` and `failure_count` across its days. A status-grouped query is not a shortcut, because each status group has a rate of 0 or 100 percent by construction. `get_metric_definition` for `success_rate` and any other rate you report, and apply the sample floor to the window's combined denominator; below it, report counts and say the rate is not yet meaningful. Sessions in the after-window are still being analysed, so a high `unanalyzed_count` makes the after-side rate provisional.
4. Find what moved: `aggregate_sessions` for the same covering range with `group_by: ["day", "intent"]` and `session_count`, `success_count`, `failure_count`, filtered by the agent. Split the day buckets into the same two windows and compare per intent. Intents that appear or disappear between the windows are as important as rate changes, but only call an intent new or gone when both windows have enough sessions for its absence to mean something.
5. `list_signals` for the covering range. Signals that fired only after the boundary are candidate regressions; `get_signal` for evidence and affected sessions.
6. Evidence: `list_sessions` filtered by `agent_name`, `from` the boundary, and `outcome: "unsuccessful"` or `user_feedback: "negative"`. Open at most three with `get_session`, and only the turn the analysis points at with `get_turn`. Then check one comparable before-window session for the same intent, so the difference is attributable to the release and not to the intent.
7. Rule out confounders before concluding: a traffic mix shift (different intents or users after the boundary), an ingestion gap on either side, a concurrent change to another agent, and the analysis lag. Pinned notes and `list_agent_attributes` help with the first two.
8. If the app's release receipt is available, reconcile with it: it reports claim consistency, the delta versus the previous release, the production window, the prompt diff, sample sessions, and related signals. Those are fractions between 0 and 1. Report disagreements between your comparison and the receipt rather than picking one.
9. If the regression or improvement is confirmed on more than one session and the numbers clear the sample floor, `save_note` with the finding, the boundary, the metrics before and after, and the intents involved. No personal data.
10. `report_outcome`.

## Output shape

```
Agent, release boundary, windows compared (days before / after), sessions on each side
Verdict: improved / regressed / unchanged / too early, with the reason in one line
Outcome metrics: before vs after table, with unanalysed share and sample floor notes
Intents that moved: new, gone, or shifted, with counts
Signals since the release: severity, evidence, affected sessions
Evidence sessions: ids and the turn each one points at (masked, minimal quotes)
Confounders considered and how they were ruled out
Recommendation: keep, watch, or roll back, and what to re-check tomorrow
Open questions (also sent as unmet_needs)
```

## Do not

- Do not compare a 12-hour after-window with a 7-day before-window without saying the after-side is provisional.
- Do not report a rate below its sample floor as a change.
- Do not attribute a change to the release when the intent mix moved at the same time.
- Do not paste transcripts; cite session ids and turn indexes.
