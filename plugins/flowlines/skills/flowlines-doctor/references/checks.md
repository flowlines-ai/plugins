# Flowlines ingestion checks by source

Production base URL: `https://api.flowlines.ai`. Replace it when the namespace runs against another deployment. None of the commands below need the API key unless stated, and the ones that do read it from a file so it never appears in a shell command, a transcript, or a process list.

## Reachability without a key

```sh
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://api.flowlines.ai/v1/traces
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://api.flowlines.ai/v1/logs
```

A `401` proves DNS, TLS, and routing work from this host and the endpoint is up. A connection error, a timeout, or a `5xx` is the problem. A `404` means the base URL is wrong.

To test with the key, put the header in a file with mode `0600` and let curl read it:

```sh
printf 'x-flowlines-api-key: %s\n' "$(cat /secure/path/flowlines-api-key)" > /secure/path/flowlines-header
chmod 600 /secure/path/flowlines-header
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://api.flowlines.ai/v1/traces \
  -H @/secure/path/flowlines-header -H 'content-type: application/x-protobuf' --data-binary ''
rm -f /secure/path/flowlines-header
```

An accepted or bad-request status with the key (`2xx` or `400`) means the key authenticates; a `401` or `403` with the key means the key is wrong, revoked, or belongs to another namespace.

## Claude Code and Codex CLI

Installed by the `flowlines-agent-observability` skill.

1. Run its `doctor.sh`. It checks that the Claude settings carry the telemetry variables and the Flowlines header, that the Codex config carries the exporter and hooks, that the three Codex hooks are present, file modes, and the relay. It also reports how many Codex events are pending in the local spool. It does not contact Flowlines.
2. Conflicting exporters: `doctor.sh` fails when the Claude settings route signals to another collector or the Codex config carries another exporter. Reinstall with `--replace-existing-otel` after the user agrees.
3. Codex hook trust: open `/hooks` in Codex and trust the Flowlines user hooks. Until then Codex may omit prompt, tool, and assistant content, and `codex exec` sends nothing through the hooks.
4. Spool: pending events live under the Flowlines state directory in `spool/`. Each hook run sends the newest event first and drains at most five older ones within a two second budget, so a backlog clears over several turns. A spool that never drains means the relay cannot reach the endpoint; use the reachability check above from the same machine.
5. Arrival: run one harmless prompt in the CLI, then `list_sessions` with `from` set a few minutes back. `from` filters on the session's start time, which is fine for a session you just created. Claude Code sessions and Codex sessions arrive under their own agent names; `list_agents` shows the exact names in this namespace.

## Instrumented MCP server

Set up by the `flowlines-mcp-observability` skill.

1. Deployment variables: `OTEL_EXPORTER_OTLP_ENDPOINT` (the base URL), `OTEL_EXPORTER_OTLP_HEADERS` with the key from a secret, and `OTEL_SERVICE_NAME`. With AGNTCY Observe, `OBSERVE_HEADERS` must mirror the header value. Confirm they are present in the running process's environment, not only in a template.
2. Emit ten tool calls carrying `reason`, `user_intent`, `session.id`, and a test `user.id`, then one `report_outcome` call.
3. In the Flowlines app, open the MCP page. Its ingestion health is derived from a durable ledger of every MCP-shaped batch:
   - **Healthy**: telemetry arrives and every accepted call was indexed within five minutes.
   - **Delayed**: accepted calls have stayed unindexed for five minutes; a Flowlines processing delay, not a client problem. Wait and re-check.
   - **Degraded**: batches arrive but no canonical call is accepted and quality issues explain why. Read the issue codes; they name the missing or malformed attribute. Fix the emitter contract.
   - **Inactive**: no MCP-shaped batch arrived in the range. The exporter, collector, or key is wrong, or the server is not being called.
   - **Unavailable**: the app cannot read ingestion accounting; a Flowlines-side outage, retry later.
4. Calls without `reason` are visible but excluded from behavioural analysis. Calls without `user_intent` report a `missing_user_intent` quality issue. Calls without a client or transport `session.id` are not associated with a session and are excluded from tool-loop detection.
5. Paused servers: Settings, MCP lists every observed server with an enabled toggle. A paused server keeps accepting raw traces but stops call facts, session turns, signal discovery, and behavioural analysis for that server.
6. Behavioural clustering needs at least 20 valid-reason calls and three distinct normalised reasons before anything appears, and the semantic map is a fixed 28-day snapshot. Their absence right after setup is not an ingestion failure.

## LangSmith and Langfuse connectors

Configured under Settings, Connectors in the Flowlines app. Namespace API keys do not authenticate the connector endpoints; use the app.

1. Status values: `disconnected`, `configured`, `invalidCredentials`, `syncing`, `paused`, with `lastValidatedAt`, `lastSyncedAt`, and a polling status.
2. Validate re-checks the provider credentials and reports the mode (`polling`, `push`, or `publicShare`), the visible projects, an estimated trace count, and the history window in days. `invalidCredentials` after validation means the provider key or project id is wrong or was rotated.
3. Sync queues an immediate pull. Polling connectors otherwise pull on their own schedule; a `lastSyncedAt` that stops advancing while the status stays `configured` is the symptom to report.
4. History: the connector only backfills the provider's history window. Older traces are not expected.
5. Arrival: imported sessions keep their original start times, and `list_sessions` filters on start time, not on when Flowlines received them, so a `from` set to the sync time can return nothing after a successful historical import. Instead, `aggregate_sessions` with `agent_name` set to the connector's agent and a range covering the provider's history window, before and after the sync, and compare `session_count`; or `get_session` on a trace id you know the provider holds.

## SDK and OTLP applications

Instrumented with the Flowlines SDKs or a plain OpenTelemetry exporter.

1. Exporter target: the base URL, not a signal path; the exporter appends `/v1/traces` and `/v1/logs`. A signal-specific endpoint variable overrides the base and must then include the path.
2. Header: `OTEL_EXPORTER_OTLP_HEADERS=x-flowlines-api-key=<secret>`. Header-per-signal variables override it.
3. Protocol: `http/protobuf`. gRPC exporters will not reach the HTTP endpoint.
4. Service name: `OTEL_SERVICE_NAME` becomes the agent name; changing it splits the agent in Flowlines.
5. Run the reachability check from the application host, then one request through the application, then `list_sessions` with `from` set a few minutes back.

## Server-side checks over the MCP server

| Symptom | Tool | Read it as |
|---|---|---|
| Nothing arrives | `get_workspace`, `list_sessions` with `from` | ingestion status per namespace; recent arrivals |
| Analysis stuck | `aggregate_sessions` grouped by `analysis_status` | `received` or `queued_for_analysis` growing, or `analysis_failed` present |
| Users unidentified | `aggregate_sessions` metric `session_count`, `include_unidentified` true vs false | identified share of sessions (never `user_count`, which excludes empty ids); then `list_agent_attributes` to find the attribute to map |
| Agent names split | `list_agents` | inconsistent service names |
| Empty turns | `get_session` on one recent session | untrusted Codex hooks, or capture disabled on the emitter |
| Known gaps | `list_notes` | already-pinned ingestion caveats |

Identity mapping itself is configured per agent in the Flowlines app under the agent's mappings (global, users, aggregates); the MCP server cannot change it.
