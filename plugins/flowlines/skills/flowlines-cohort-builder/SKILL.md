---
name: flowlines-cohort-builder
description: Turn a question about a group of users ("which users do X", "who is at risk", "how do power users differ") into a Flowlines cohort - size it, express it in Flowlines cohort rules, hand the definition to the app, and compare it against a baseline over the Flowlines MCP server. Use when the user asks about segments, populations, or comparing groups of users.
---

# Flowlines cohort builder

A cohort is a saved rule set over a user aggregate that Flowlines keeps up to date and can compare against other cohorts. This skill sizes a candidate group with the MCP tools, writes the definition in the exact rule vocabulary, and verifies it once it exists.

## Conventions for every Flowlines tool call

- Every tool takes `reason` and `user_intent`. Keep `user_intent` identical across the conversation, for example "Identify users who churned after a frustrated session".
- Start with `get_workspace` once, then `get_context`. Pinned notes may already describe the population the user is asking about.
- Cohorts are about people. Report them in aggregate; open individual users only to validate a rule, and mask identifiers.
- End with `report_outcome` as the last tool call.

## What the MCP server can and cannot do

The MCP server reads cohorts and compares them: `list_cohorts`, `get_cohort`, `compare_cohorts`, plus `list_users`, `get_user_population_map`, and `aggregate_sessions` with `cohort_ids` and `group_by: ["cohort"]`. Creating or editing a cohort happens in the Flowlines app, in the cohort builder on the Users view, or through the REST API with a signed-in user session. Namespace API keys only authenticate ingestion, so this skill produces a definition ready to paste into the builder and verifies the result afterwards.

## Steps

1. Restate the question as a rule. Every cohort rule has a `kind`; the vocabulary and operators are in [references/cohort-rules.md](references/cohort-rules.md). Examples:
   - "users who had a frustrated session in the last 14 days": `facetSentiment includes ["frustrated"]` with `windowDays: 14`.
   - "power users": `numeric powerScore gte <threshold>` or `numeric sessionCount gte <n>`.
   - "at-risk accounts": `numeric successRate lt 50` (rates are 0 to 100) and `recency inLastDays 30`.
   - "everyone who asked about refunds": `intentFamily isOneOf ["refund"]`, using intent names from `aggregate_sessions` grouped by `intent`.
2. `list_cohorts`. Reuse an existing or system cohort when one already expresses the question; note `matchedCount`, `totalCount`, and `matchedPercent`.
3. Size the candidate group before creating anything. Use `list_users` with `order_by`, `minimum_sessions`, and `range` for count-based rules, `get_user_population_map` for a distribution, and `aggregate_sessions` grouped by `user` with the relevant filter for intent- or outcome-based rules. Report the estimated size and the identified share of sessions: `aggregate_sessions` with metric `session_count`, once with `include_unidentified: true` and once with `false`, divided. A cohort over mostly unidentified sessions is not actionable.
4. Validate the rule on two or three users from the estimate with `get_user_activity`. Confirm they belong for the reason the user cares about, not by coincidence.
5. Hand over the definition: name, one-line description, the aggregate (the users aggregate unless the user says otherwise), and the rules as JSON in the vocabulary. The app's rule suggestions can propose alternatives; mention them when the rule is a stretch.
6. After the user creates it, `get_cohort` to confirm `ruleCount`, `matchedCount`, and `totalCount` match the estimate. A large mismatch usually means a `windowDays` or a threshold differs from the estimate's range.
7. Compare: `compare_cohorts` against the baseline (usually the all-users system cohort or a mirror-image cohort), with `range` `7d`, `30d`, or `all`. The comparison reports entity count, session count, clean session rate, success rate, average cost, average latency, and signal rate for both sides; the rates are percentages from 0 to 100. `get_metric_definition` before interpreting a rate.
8. Pin the definition and the headline comparison with `save_note` only if the cohort will be used again, and never with per-user detail.
9. `report_outcome`.

## Output shape

```
Question, restated as a rule
Definition: name, description, aggregate, rules (JSON)
Estimated size: users matched of total, identified share, top examples validated (masked)
Comparison vs baseline: table of the compare_cohorts metrics
What the cohort is good for and what it cannot tell you
Open questions (also sent as unmet_needs)
```

## Do not

- Do not create a cohort over unidentified users and present it as a customer segment.
- Do not report a rate from a cohort smaller than the metric's sample floor.
- Do not list users by name in the answer; counts and masked examples only.
