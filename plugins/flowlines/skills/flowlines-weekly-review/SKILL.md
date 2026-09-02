---
name: flowlines-weekly-review
description: Produce a periodic review of a Flowlines namespace over the Flowlines MCP server - what changed since the last review, which signals fired, where outcomes moved, and what to pin for next time. Use when the user asks what changed, wants a weekly or monthly review, or asks for a status report on their agents.
---

# Flowlines weekly review

Turn the Flowlines MCP tools into one repeatable review with a fixed shape, so successive reviews are comparable and nothing already known is re-derived.

## Conventions for every Flowlines tool call

- Every tool takes `reason` (why this call) and `user_intent` (the user's goal, identical across the conversation). Set `user_intent` once, for example "Weekly review of the <namespace> namespace".
- Start with `get_workspace` once, pick the namespace, then `get_context` for that namespace. Read its pinned notes and glossary before analysing: notes record known caveats and confirmed findings.
- Prefer aggregates over transcripts. Open a session only as evidence for a claim, quote the minimum, and mask names, emails, and other identifiers.
- End with `report_outcome` as the last tool call, before the final answer, with `unmet_needs` for anything the server could not provide.

## Inputs

Ask for, or infer, three things:

1. The namespace. If `get_workspace` shows exactly one, use it silently.
2. The review window. Default to the last 7 days. `get_changes_since` needs an ISO 8601 `since` timestamp and clamps to the trailing 90 days; take `since` from the previous review's pinned note when one exists, otherwise from the window.
3. Focus agents, if the user names any. Otherwise cover every agent with activity.

## Steps

1. `get_context` with `overview_range` matching the window (`7d` for a weekly review, `30d` for a monthly one). Record the context status; if it is `not_configured`, `gathering`, or `failed`, say so and continue without it.
2. `list_notes`. Find the most recent note whose title starts with `Weekly review` and take `since` from its body. Titles carry the review date, so each period has its own note.
3. `get_changes_since` with `since`. This returns session activity and outcomes in the window, signals that fired, and notes pinned. It replaces separate list calls.
4. `aggregate_sessions` for the window with `group_by: ["agent"]` and metrics `session_count`, `user_count`, `success_count`, `failure_count`, `success_rate`, `total_cost_usd`, `unanalyzed_count`. Run it again with `group_by: ["day"]` for the trend. Never average rates across groups or days: a rate for any combination of groups is the summed `success_count` divided by the summed `success_count` plus `failure_count`. When a rate looks surprising, `get_metric_definition` for it before interpreting: denominators, missing-data rules, and sample floors differ by metric.
5. `list_signals` for the window. For each signal that is new or grew, `get_signal` for its evidence. Group signals by agent and severity.
6. For the largest movements, `aggregate_sessions` with `group_by: ["intent"]` on the affected agent to see which intents drive the change, then `list_sessions` filtered by `outcome: "unsuccessful"` or `user_feedback: "negative"` and open at most three sessions with `get_session` as evidence.
7. Check identity coverage: `aggregate_sessions` with metric `session_count`, once with `include_unidentified: true` and once with `false`. The identified share is the second count divided by the first. `user_count` cannot show this gap because it never counts empty user ids. A low identified share means identity mapping is incomplete; report it rather than drawing user-level conclusions.
8. Decide what to pin. `save_note` only for durable, verified findings that the next review must not rediscover: an evaluator artifact, an ingestion gap, a confirmed regression and its cause. Never put end-user personal data in a note.
9. Save the continuation point. Pin one note titled `Weekly review <review date>`, for example `Weekly review 2026-09-02`, whose body records the review timestamp to use as the next `since`, the window covered, and the two or three headline numbers. The date in the title makes each period's note distinct; the server rejects a title it has seen recently regardless of the body, and notes cannot be edited. If the save is rejected as a duplicate, the period was already reviewed: `list_notes`, confirm the existing note covers this window, and reuse its timestamp. Pass `allow_duplicate: true` only when the existing note is for a different window and the title collided anyway. Confirm the save succeeded and the timestamp is recorded before reporting the review as complete.
10. `report_outcome`.

## Output shape

Use this structure every time so reviews line up week over week:

```
Namespace, window, review timestamp (use it as the next `since`)
Headline: 3 bullets, each with the number and the change versus the previous window
Outcomes by agent: table of sessions, users, success rate, cost, unanalysed
Signals: new, grown, resolved - each with severity, agent, one-line evidence
Notable intents: the intents behind the largest movements
Data quality: unanalysed share, unidentified users, context status, anything pinned as a caveat
Pinned this review: titles of notes saved, including the dated review note and its timestamp
Open questions: what the server could not answer (also sent as unmet_needs)
```

Report numbers with their metric definitions in mind: an `unanalyzed_count` above a few percent makes `success_rate` provisional, and a rate below the metric's sample floor is not a trend. Say when a comparison is against a partial previous window.

## Do not

- Do not page through `list_sessions` to build totals; `aggregate_sessions` exists for that.
- Do not average rates across groups; recompute from summed counts.
- Do not quote prompts or responses beyond the minimum needed to support a finding.
- Do not pin conversation scratch, hunches, or per-user observations.
- Do not skip `report_outcome`, including when the review is empty or blocked.
