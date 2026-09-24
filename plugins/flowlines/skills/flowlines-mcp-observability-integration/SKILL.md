---
name: flowlines-mcp-observability-integration
description: Integrate, repair, review, or verify Flowlines observability in an MCP server repository. Use when a server must emit canonical Flowlines MCP tool-call telemetry through AGNTCY Observe or vanilla OpenTelemetry; do not use for Claude Code or Codex CLI telemetry.
---

# Flowlines MCP Observability

Instrument an MCP server so complete tool executions arrive in Flowlines as canonical MCP calls. Modify the target server; do not add a Flowlines runtime SDK or assume ownership of unrelated telemetry.

## Consent and secrets

Before changing code or deployment configuration:

1. Explain that supported MCP spans export validated tool arguments, final client-visible results, and user identity metadata to Flowlines. Identity metadata includes a stable user ID and, when available, name and email; these fields and payloads may contain personal data, customer data, source code, file content, or other sensitive values.
2. Obtain explicit consent for payload export. Do not infer it from a generic request to "add telemetry."
3. Confirm the user has a Flowlines namespace API key before touching the deployment. First make sure the `flowlines` MCP server is signed in; if it is not, ask the user to sign in with their app's sign-in button for the `flowlines` server; only in a terminal CLI, name `/mcp` (Claude Code) or `codex mcp login flowlines` (Codex). Signing in also creates their Flowlines account. Then call `get_workspace`. If it returns no organization or namespace, or the user has no key for the namespace that should receive the data, open `https://app.flowlines.ai/get-started?agent=claude-code` for them (`agent=codex` when you run in Codex) with `open` on macOS or `xdg-open` on Linux, or give them the link. Open it only after `get_workspace` succeeds, because the page treats the `agent` value as a connected agent. Explain that the page creates their workspace and a namespace API key, then waits for the first tool call. The key is shown once, inside a ready-to-paste block of the OTLP environment variables. Ask the user to place it in the target deployment's secret manager; a local git-ignored env file is fine for a local test run. Never request the key in chat, write it into source or examples, interpolate it into a command, or print an existing value.
4. Treat the integration request as permission to edit and test the target repository, not to deploy it, call production tools, or mutate any production database.

Read [references/contract.md](references/contract.md) before implementing or reviewing an integration.

## Inspect the target first

Read the repository instructions, architecture documentation, and testing strategy. Then identify:

- language, runtime, MCP SDK and transport;
- package manager, lockfile, dependency policies, and supported runtime versions;
- the central tool-registration or dispatch boundary;
- existing MCP-level middleware or interceptors;
- existing OpenTelemetry provider, exporter, collector, propagation, and shutdown handling;
- where validated arguments, request ID, request `_meta`, the MCP transport session ID, authenticated user ID/profile, final MCP result, and error mapping are available;
- how deployment secrets and environment variables are declared without values.

Preserve the target's package manager and telemetry ownership. Reuse an existing tracer provider and collector when present; never register a competing global provider or replace unrelated exporters.

## Mandatory session and user identity

Every emitted MCP span, `report_outcome` included, must carry `session.id`. There is no exception. Every span must also carry `user.id`, unless there is truly no way to identify the user. Find both sources while you inspect the target, before you write span code. An integration that does not send them is not complete.

Without `session.id`, Flowlines cannot put the call in a session: there is no session intent or outcome, `report_outcome` links to nothing, tool loops are not detected, and every call raises a `missing_session_identity` quality issue. Without `user.id`, no call is attributed to a user, so user lists, new-user signals, cohorts, and per-user activity stay empty for this server.

Resolve `session.id` from the first available source:

1. Client `_meta["session.id"]`: the conversation ID that the host or agent supplies.
2. When the operator controls the MCP client, for example its own agent, change the client to send `_meta["session.id"]` instead of using a fallback.
3. The MCP transport session: the `Mcp-Session-Id` of a Streamable HTTP session or, on stdio, one fresh ID generated when the connection starts. Flowlines does not read `mcp.session.id` as a session, so emit this value as `session.id`, and also as `mcp.session.id` so its source stays visible.
4. If the server runs stateless HTTP without MCP session IDs, enable session IDs on the transport. If the deployment cannot support that, stop and ask the user. Do not ship the integration without `session.id`.

A transport session is not always one conversation: a long-lived connection can hold several conversations, and a reconnect can split one. Report this limitation when you use source 3. Never derive a session from the user, trace ID, timing, IP address, tool arguments, or a reused JSON-RPC request ID.

Resolve `user.id` from the first available source:

1. The verified authenticated subject: the OAuth `sub`, the signed-in user, or the user who owns the API key. If the server authenticates requests at all, a stable user ID exists; trace it from the authentication layer to the tool-call boundary. When authentication identifies only a shared account, use the account ID and say so in the hand-off.
2. Client `_meta["user.id"]`, as an untrusted analytics value.
3. When the operator controls the MCP client, change the client to send `_meta["user.id"]`.

Omit `user.id` only when all of these are true: the server verifies no caller identity, its clients are third-party hosts that cannot be changed to send `_meta["user.id"]`, and the user confirms that adding authentication or client metadata is out of scope. Then emit no `user.id`, and report the missing identity and its consequences in the hand-off. Never fill `user.id` with an email address, display name, session ID, trace ID, IP address, OAuth client ID, or generated ID.

## Choose the integration path

- For a compatible Python server using the official `mcp` package, prefer AGNTCY Observe. Read [references/python-agntcy.md](references/python-agntcy.md).
- For TypeScript or any other language with an OpenTelemetry SDK, use vanilla OpenTelemetry. Read [references/vanilla-opentelemetry.md](references/vanilla-opentelemetry.md).
- On the vanilla path, prefer the framework's existing MCP-level middleware or interceptor at `tools/call` as the default span boundary. Typical hooks: Go `AddReceivingMiddleware`, FastMCP `on_call_tool`, official Python `server.middleware` filtered to `tools/call`, or the equivalent TypeScript hook. Do not use HTTP, transport, or sending middleware as the Flowlines MCP span boundary; resolve identity from those layers when needed, then emit the span at MCP `tools/call`.
- If automatic instrumentation or that middleware hook cannot observe the final client-visible result, validated arguments, or request metadata, keep a single wrapper around the central tool execution boundary and capture the missing fields there. Do not scatter nearly identical span code across every handler unless the framework provides no shared boundary. Do not emit Flowlines MCP spans for `initialize`, `tools/list`, or other non-`tools/call` methods. Disable overlapping automatic coverage so each call produces one Flowlines MCP span.

If the stack has neither supported AGNTCY instrumentation nor a usable OpenTelemetry SDK, explain the gap instead of inventing an unverified exporter or protocol adapter.

## Implement the contract

Make the smallest coherent change that satisfies all of these invariants:

1. Require non-empty `reason` and `user_intent` strings in every ordinary tool input schema. Do not synthesize either value from prompts or tool arguments. Update server instructions, examples, affected callers, and tests because this is an intentional schema change.
2. Register `report_outcome` exactly as described in the contract and include its unconditional final-call instruction in the server instructions.
3. Start one server span around each complete, validated `tools/call` execution. Give every invocation a fresh tool-call ID that is independent of the JSON-RPC request ID.
4. Record the canonical attributes from `contract.md`, the validated tool-argument object, and only the final MCP result returned to the client. When the tool has a published description, emit it as `gen_ai.tool.description` from the registration metadata, trimmed and capped at 10,000 characters. Omit missing descriptions; do not infer them from arguments or reasons. Emit the tool's published input schema as `gen_ai.tool.input_schema`, and its output schema when declared as `gen_ai.tool.output_schema`, serialized whole from the same registration metadata; omit a schema that is missing or would exceed 50,000 characters.
5. Put a non-empty, stable user identifier on every emitted MCP span as the exact `user.id` attribute, from the source order in **Mandatory session and user identity**, which also defines the only case where it may be omitted. Verified identity wins over client metadata.
6. When verified profile name/email exists, emit it on the same span as exact `user.name` and `user.email` attributes. Otherwise promote non-empty client metadata as untrusted analytics values and document that provenance. Verified fields always win. Flowlines does not map name or email merely because they remain nested in MCP `_meta`; treat them as PII and never put them in captured tool arguments.
7. Specify the applicable Flowlines identity mapping, for the user to save in the Flowlines app and for you to verify after deployment, with user ID attribute `user.id`, name field ID `name` mapped to `user.name`, and email field ID `email` mapped to `user.email`. Use the caller-agent users mapping when a real caller agent is present, or the equivalent namespace identifier mapping for an agentless MCP session. Never label the MCP server as a caller agent. Sending the attributes alone is not sufficient for name/email profile enrichment when identity fields have not been mapped; if neither mapping surface is available, report that limitation explicitly.
8. Put a non-empty `session.id` on every emitted MCP span, `report_outcome` included, from the source order in **Mandatory session and user identity**.
9. Propagate valid incoming W3C trace context when the transport exposes it. Do not make trace context a prerequisite for a call to be recorded.
10. Mark every completed call explicitly: set span status to `OK` after a successful final MCP result and `ERROR` for a tool or protocol failure. Do not leave a completed call at the OpenTelemetry default `UNSET`, because Flowlines reports that call's success as unknown. On failure, record only a bounded error type; do not record raw exceptions, stack traces, authorization headers, OAuth claims, request `_meta`, environment variables, or secret-bearing diagnostics.
11. Keep telemetry fail-open. Export failure must not change the MCP response, and shutdown flushing must be bounded.
12. Configure OTLP through environment variables or the existing collector. Commit only secret placeholders and variable names.

Do not change sampling for an application-wide provider without explicit approval. A dedicated MCP provider may use always-on sampling because these spans are product facts; with a shared provider, preserve its policy and call out any risk from unsampled remote parents.

## Verify locally

Add tests at the middleware or wrapper boundary, using the stack's in-memory exporter when available. At minimum cover:

- a successful call with explicit `OK` span status, required attributes, distinct call/request IDs, stable `user.id`, arguments, and result;
- `session.id` on every span, `report_outcome` included, from `_meta["session.id"]` when present and from the transport session otherwise;
- when `user.id` is omitted under the rule above, no substitute or generated `user.id` on any span;
- the registered tool description as `gen_ai.tool.description`, with trimming and the 10,000-character bound, plus omission when no description exists;
- the registered input and output schemas as `gen_ai.tool.input_schema` and `gen_ai.tool.output_schema`, serialized whole and identical to what `tools/list` publishes, plus omission when absent or over the 50,000-character bound;
- exact `user.name` and `user.email` span attributes for both the verified-profile path and the client-metadata fallback when those values are available;
- a failed call with explicit `ERROR` span status that exports only the safe client-visible error and a bounded error type;
- absence of `_meta`, authorization material, raw exception messages, and spoofed identity; verified identity must win over all client-supplied user fields;
- `report_outcome` schema and server instructions;
- exporter shutdown or force-flush behavior when the integration owns the provider.

Run the target repository's narrow tests, formatter/linter, type checker, and package-manager checks. Never put a real API key in a test.

## Review the integration

When the local checks pass, review the complete diff before you hand it off. The review is a gate, not a summary. When the client can start a subagent or reviewer with fresh context, give it the diff, this file, and [references/contract.md](references/contract.md); otherwise reread the diff yourself against them. Check that:

- every numbered invariant in **Implement the contract** and every rule in **Mandatory session and user identity** holds;
- each `tools/call` produces exactly one Flowlines MCP span, with no duplicate from automatic instrumentation and no span for `initialize`, `tools/list`, or other methods;
- every ordinary tool schema requires `reason` and `user_intent`, and the server instructions, examples, callers, and tests match;
- no secret, request `_meta`, authorization material, raw exception, or stack trace reaches a span, a log, a test, or a committed file;
- telemetry stays fail-open, shutdown flushing is bounded, and the change adds no second global provider and no sampling change;
- the tests cover every case in **Verify locally** and fail when the behavior they cover is removed.

Fix each finding, rerun the local checks, and review again until the review finds nothing. Report any finding that you choose not to fix, with the reason, in the hand-off.

## Hand off and deploy

Do not deploy the integration yourself. Report:

- files and dependencies changed;
- where deployment must set the endpoint, API-key header, and service name;
- the source of `session.id` (client metadata or transport fallback) and of `user.id`, or why `user.id` is absent and what the user confirmed;
- availability of name/email, and the exact Flowlines user mappings to configure;
- schema or client compatibility changes caused by `reason`, `user_intent`, or `report_outcome`;
- checks run, and review findings fixed or left open;
- any identity, propagation, sampling, payload, or shutdown limitation that remains.

Then ask the user to deploy:

1. Set the endpoint, the API-key header from the deployment's secret manager, and the service name in the deployment environment, plus `OBSERVE_HEADERS` on the AGNTCY path.
2. Deploy the server, and the updated MCP clients when the change asks clients to send `_meta["session.id"]` or `_meta["user.id"]`.
3. Save the identity mapping from invariant 7 in the Flowlines app before the first real calls. Existing sessions are not enriched retroactively.

Then offer to use the Flowlines MCP server to confirm that the deployed integration works. Run the check only when the user accepts.

## Confirm in Flowlines

Use the `flowlines` MCP server that this plugin installs. Follow its conventions: pass `reason` and `user_intent` on each call, and end with its own `report_outcome`, not the one you added to the target server.

1. Traffic. After the deployment is live, ask the user to run one short conversation through a real MCP client that uses the server. Alternatively, when the user authorizes it and the deployed server is reachable, make ten harmless calls that share a test `session.id` and test `user.id`, with a test name/email when supported, then one final `report_outcome` call in the same session. Note the time before the first call and the expected user ID.
2. `get_workspace`: find the namespace that the deployment's API key writes to.
3. `list_sessions` with `from` set to that time, and `user_id` set to the expected user ID when `user.id` is emitted. Sessions normally appear within minutes. If nothing appears, repeat without `user_id`: a session that appears only then has lost its user identity, and no session at all points at the export path.
4. `get_session` on the new session: confirm that it holds every call, `report_outcome` included. Calls spread over several sessions mean that `session.id` is not stable.
5. `get_user_activity` with the expected user ID, and `list_users` (most recently active first by default): confirm that the calls map to that user, and that `identity.name` and `identity.email` show once the mapping is saved. Skip this step only when `user.id` is omitted under the no-identity rule, and say so.
6. `get_mcp_overview` with the namespace ID and `range` `24h`: expect `ingestion.acceptedCallCount` to reach at least the number of test calls, eleven when you made them (it counts every call the namespace accepted in the range), and `ingestion.status` `healthy`. Pending calls, or a brief `delayed`, right after the test calls are normal; wait a short while and call it again. `degraded` means MCP-shaped telemetry arrived but no canonical call was accepted, and `qualityIssueCount` counts the quality issues that explain why; check the emitter against the contract. `inactive` means no MCP-shaped batch arrived in the range; check the exporter endpoint and API key. `unavailable` means Flowlines cannot read ingestion accounting; retry later. If the server does not offer `get_mcp_overview`, ask the user to read ingestion health on the MCP page of the Flowlines app, or on the get-started page, which turns green on the first call.
7. Quality issues such as `missing_session_identity`, and successful versus unknown call status, appear on the MCP page of the Flowlines app, not over MCP. Ask the user to read them there.

Report what each step confirmed, what the user read in the app, and what remains unverified. Behavioral clustering and tool-loop signals have separate volume and timing thresholds, so do not treat their immediate absence as exporter failure.

Verifying receipt and the identity mapping needs the Flowlines MCP server signed in. If authentication is required, or a generic MCP error (such as `-32603`) repeats on one read-only check, use `flowlines-doctor` for connection recovery. Client diagnostics and native sign-in are allowed for this repair; resume receipt verification after tool access is restored.

If the connection remains unavailable, name the exact mapping to configure (`user.id` as the user ID, `name` to `user.name`, `email` to `user.email`) and where in the Flowlines app the user can configure and check it, and say that receipt was not verified. Do not open the app, drive a browser, or search the web to verify it yourself unless the user explicitly asks.
