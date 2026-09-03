---
name: flowlines-doctor
description: Diagnose why data is not arriving in Flowlines, or is arriving incomplete, across every source - Claude Code and Codex telemetry, an instrumented MCP server, LangSmith or Langfuse connectors, and OTLP from an SDK-instrumented app - using local checks, the Flowlines MCP server, and the Flowlines app. Use when sessions are missing, analysis is stuck, users are unidentified, or an integration was just set up and needs verification.
---

# Flowlines doctor

Work from the source towards Flowlines and stop at the first broken link. Each check states what it proves, so a green result is not mistaken for "everything works".

## Conventions

- Flowlines MCP tools take `reason` and `user_intent`; keep `user_intent` identical, for example "Find out why Codex sessions stopped appearing in Flowlines".
- Never print, echo, or paste a Flowlines API key. Reachability checks below work without one, and checks that need one read it from a file the user created.
- End with `report_outcome` as the last Flowlines tool call, listing what could not be checked.

## Step 1: what should be arriving

Ask which sources the namespace expects, or infer them:

- `get_workspace` lists every namespace with its ingestion status; pick the namespace and note whether it has ever received data.
- `get_context` returns the activity overview and the agent glossary; `list_agents` shows what has actually been observed. An expected agent that is absent from `list_agents` has never been ingested under that name.
- `list_sessions` with `from` set to the last hour or day shows whether anything is arriving right now. `from` filters on session start time, not ingestion time, so it suits live sources; imported history keeps its original dates. Sessions normally appear within minutes; analysis follows later.

Record the expected sources before checking any of them.

## Step 2: check each source

Full procedures per source are in [references/checks.md](references/checks.md). In short:

- **Claude Code or Codex telemetry.** Claude Code exports through its OpenTelemetry settings and Codex through its `[otel]` exporter plus user hooks. Check those settings against the reference, run one harmless prompt, and look for the session with `list_sessions` filtered to the last few minutes. For Codex, hooks must be trusted in `/hooks` before prompt and tool content arrive.
- **An instrumented MCP server.** Confirm the OTLP environment variables are set in the deployment, run ten tool calls plus `report_outcome`, then read the ingestion health status on the MCP page of the Flowlines app. The five statuses and what each one implicates are in the reference. A paused server under Settings, MCP stops derived observability without stopping ingestion.
- **LangSmith or Langfuse connectors.** Status lives under Settings, Connectors in the app: `disconnected`, `configured`, `invalidCredentials`, `syncing`, or `paused`, with the last validation and sync times. Validate, then queue a sync, then verify arrival over the provider's history window, since imported sessions keep their original dates.
- **SDK or OTLP applications.** Check that the exporter points at the Flowlines base URL, that `/v1/traces` and `/v1/logs` are reachable from the host, and that the key header is set from a secret.

## Step 3: server-side symptoms

When data arrives but looks wrong, these tools locate the problem without opening transcripts:

- Analysis stuck: `aggregate_sessions` grouped by `analysis_status` for `24h` and `7d`. A growing `received` or `queued_for_analysis` share, or any `analysis_failed`, is a processing problem, not an ingestion one.
- Users unidentified: `aggregate_sessions` with metric `session_count`, once with `include_unidentified: true` and once with `false`; the identified share is the second divided by the first. Do not use `user_count` for this, it never counts empty user ids. A low share means identity mapping is incomplete; `list_agent_attributes` shows which attributes arrive so the right one can be mapped in the app.
- Agents split or misnamed: `list_agents` shows near-duplicate names caused by inconsistent service names.
- Content missing from sessions: `get_session` on one recent session and confirm the turn tree has user and assistant content. Empty turns on Codex point at untrusted hooks; empty MCP tool payloads point at the instrumented server's capture settings.
- Known artifacts: `list_notes` before concluding anything; ingestion gaps are often already pinned.

## Step 4: report

```
Namespace and expected sources
Per source: status (working / broken / not verifiable here), what was checked, the evidence, the next action
Server-side symptoms found: analysis lag, unidentified share, naming, missing content
What needs the Flowlines app or a deployment change, and where
Pinned: any durable ingestion gap saved with save_note (no personal data)
Open questions (also sent as unmet_needs)
```

If a durable gap is confirmed, such as a source that stopped on a known date, `save_note` it so the next analysis accounts for the hole.
