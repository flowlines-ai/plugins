---
name: flowlines-investigate-session
description: Investigate a specific problem in Flowlines - a signal, a user complaint, a failed session, or a suspicious pattern - from the aggregate down to the exact turn, over the Flowlines MCP server, while handling end-user data with care. Use when the user asks why something went wrong, wants to look into a signal or a user's sessions, or needs evidence for a bug report.
---

# Flowlines session investigation

Go from a symptom to a verifiable cause with the smallest exposure of end-user content. Aggregates first, then the session, then only the turns that matter.

## Conventions for every Flowlines tool call

- Every tool takes `reason` and `user_intent`. Keep `user_intent` identical across the conversation, for example "Find out why the billing agent fails on refund requests".
- Start with `get_workspace` once, then `get_context` for the namespace. Read pinned notes first: the problem may already be a known artifact.
- Flowlines data is real production conversations. Quote the minimum, mask names, emails, phone numbers, addresses, identifiers, and payment details, and never copy a transcript into a note, ticket, or report.
- End with `report_outcome` as the last tool call.

## Starting points

Pick the entry that matches what the user has:

- **A signal.** `list_signals` to find it, then `get_signal` for evidence and affected sessions and users.
- **A user.** `get_user_activity` for the timeline, outcomes, agents, intents, signals, and representative sessions. Prefer this over listing that user's sessions.
- **A session id.** `get_session` directly.
- **A description.** `search` with `types` narrowed to `session` or `turn`, a time window, and the agent, then `fetch` the locators worth opening.
- **A pattern.** `aggregate_sessions` grouped by `intent`, `agent`, or `day` with `failure_rate` and `failure_count`, ordered by the metric, to find where the problem concentrates before opening anything.

## Steps

1. Scope the problem with aggregates. Establish how many sessions, users, and days are affected and whether it is growing. `get_metric_definition` for any rate you quote.
2. Choose at most five representative sessions: the earliest, the most recent, and the ones the signal or user activity points at. `list_sessions` with `outcome`, `user_feedback`, `intent_family`, `from`, and `to` narrows the pick.
3. `get_session` for each. Read the analysis and the turn tree before any content: the session summary, outcome, and findings often name the failing turn.
4. `get_turn` only for the turns the analysis points at. Compare the user's request, the tool calls, and the assistant reply on that turn. Look for the usual causes: wrong intent classification, a tool error surfaced as a normal reply, missing context, a policy refusal, a loop, or a truncated response.
5. Check whether the cause is upstream of the agent: an ingestion gap (turns missing, timestamps out of order), an unmapped user identity, or an evaluator artifact. Pinned notes and `list_agent_attributes` help here.
6. Confirm the cause on a second session before calling it a cause. One session is an anecdote.
7. Estimate blast radius with one more `aggregate_sessions` filtered to the intent or agent, and check `list_signals` for a signal that already tracks it.
8. If the finding is durable and verified, `save_note` with the finding, the evidence in aggregate terms, and how future analysis should account for it. Never include personal data in the note.
9. `report_outcome`.

## Output shape

```
Symptom: what was reported, in one line
Scope: sessions, users, agents, first and last occurrence, trend
Cause: the mechanism, with the turn-level evidence (masked, minimal quotes)
Confirmed on: session ids used as evidence
Blast radius: share of sessions for the intent or agent in the window
Related signals and notes
Recommended fix or next check
Open questions (also sent as unmet_needs)
```

## Handling content

- Reference sessions and turns by id and index, not by pasting them.
- When a quote is unavoidable, keep it to the fragment that proves the point and replace identifiers with placeholders such as `<email>`.
- Do not reproduce prompts, system instructions, or tool payloads in full.
- If the user asks for a full transcript, point them to the session in the Flowlines app rather than reproducing it here.
