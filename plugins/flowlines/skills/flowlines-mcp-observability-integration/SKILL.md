---
name: flowlines-mcp-observability-integration
description: Integrate, repair, review, or verify Flowlines observability in an MCP server repository. Use when a server must emit canonical Flowlines MCP tool-call telemetry through AGNTCY Observe or vanilla OpenTelemetry; do not use for Claude Code or Codex CLI telemetry.
---

# Flowlines MCP Observability

Instrument an MCP server so complete tool executions arrive in Flowlines as canonical MCP calls. Modify the target server; do not add a Flowlines runtime SDK or assume ownership of unrelated telemetry.

## Consent and secrets

Before changing code or deployment configuration:

1. Explain that supported MCP spans export validated tool arguments, final client-visible results, and a stable user ID to Flowlines; these payloads may contain personal data, customer data, source code, file content, or other sensitive values.
2. Obtain explicit consent for payload export. Do not infer it from a generic request to "add telemetry."
3. Ask separately whether to send each end user's name and email. Explain the trade-off. Without them, Flowlines shows most of the server's users as raw IDs, because it can only fill in a profile for people who have a Flowlines account. With them, the operator sends personal data about its own users to Flowlines as a third party, so its privacy policy or data processing terms must cover that. When the user declines, send neither and skip **End-user name and email**.
4. Confirm the user has a Flowlines namespace API key before touching the deployment. If they do not, tell them to create one in the Flowlines app under Settings, API keys, at `https://app.flowlines.ai/settings` for the namespace that should receive the data, and offer to open that page for them (`open` on macOS, `xdg-open` on Linux). The key is shown once at creation. Ask the user to place it in the target deployment's secret manager. Never request the key in chat, write it into source or examples, interpolate it into a command, or print an existing value.
5. Treat the integration request as permission to edit and test the target repository, not to deploy it, call production tools, or mutate any production database.

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

## End-user name and email

When the user agreed to send them, look for each end user's name and email while you inspect the target, the same way you look for `user.id`. Flowlines fills in a profile only for people who have a Flowlines account, so for the server's own users these attributes are the only source. Do not stop because the token the server checks carries only a subject: the name and email usually exist elsewhere.

Resolve `user.name` and `user.email` from the first source that has them:

1. Profile claims that the authentication layer already verified: `name` and `email` in the ID token or JWT, or on the user or session object that the auth middleware attaches to the request.
2. The server's own record for the verified subject: its users table, the account profile it already loads, or the owner of the API key.
3. The identity provider's userinfo endpoint, called with the access token that the server already verified, when the provider supports it.
4. Client `_meta["user.name"]` and `_meta["user.email"]`, as untrusted analytics values. When the operator controls the MCP client, change the client to send them.

Cache the results of sources 2 and 3 per user, with a bounded size and expiry, so that a tool call does not add a database or network round trip each time. A lookup must never change the MCP response or noticeably delay it: bound it with a short timeout, and when it fails or times out, export the span with `user.id` and without name or email. When `user.id` is a shared account, do not attach one person's name or email to it.

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
6. When the user agreed to send name and email, emit them on the same span as exact `user.name` and `user.email` attributes, from the source order in **End-user name and email**. Server-side values always win over client metadata; document the provenance of client-supplied values. Flowlines does not read name or email that remain nested in MCP `_meta`; treat them as PII and never put them in captured tool arguments. When the user declined, emit neither, even when the client sends them.
7. Do not ask the user to save a Flowlines identity mapping for these attributes: Flowlines reads exact `user.id`, `user.name`, and `user.email` from canonical MCP spans without one. A mapping already saved in the Flowlines app, on a caller agent or on the namespace, overrides them, so ask the user to check that any existing mapping does not point the user ID, name, or email at other attributes.
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
- exact `user.name` and `user.email` span attributes for both the server-side path and the client-metadata fallback when those values are available;
- when name and email come from a lookup, one lookup per user across repeated calls, and a failed or timed-out lookup that still exports the span with `user.id`, without name or email, and returns the MCP response unchanged;
- when the user declined name and email, neither attribute on any span, even when the client sends them;
- a failed call with explicit `ERROR` span status that exports only the safe client-visible error and a bounded error type;
- absence of `_meta`, authorization material, raw exception messages, and spoofed identity; verified identity must win over all client-supplied user fields;
- `report_outcome` schema and server instructions;
- exporter shutdown or force-flush behavior when the integration owns the provider.

Run the target repository's narrow tests, formatter/linter, type checker, and package-manager checks. Never put a real API key in a test.

## Review the integration

When the local checks pass, review the complete diff before you hand it off. The review is a gate, not a summary. When the client can start a subagent or reviewer with fresh context, give it the diff, this file, and [references/contract.md](references/contract.md); otherwise reread the diff yourself against them. Check that:

- every numbered invariant in **Implement the contract** and every rule in **Mandatory session and user identity** holds;
- when the user agreed, name and email are sent whenever a source in **End-user name and email** has them. A server that authenticates its users but sends neither is a finding, unless the hand-off names each source you checked and why it had nothing;
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
- whether name and email are sent and the source of each (verified claims, the server's user record, userinfo, or client metadata); otherwise, that the user declined, or which sources you checked and why each had nothing;
- schema or client compatibility changes caused by `reason`, `user_intent`, or `report_outcome`;
- checks run, and review findings fixed or left open;
- any identity, propagation, sampling, payload, or shutdown limitation that remains.

Then ask the user to deploy:

1. Set the endpoint, the API-key header from the deployment's secret manager, and the service name in the deployment environment, plus `OBSERVE_HEADERS` on the AGNTCY path.
2. Deploy the server, and the updated MCP clients when the change asks clients to send `_meta["session.id"]`, `_meta["user.id"]`, `_meta["user.name"]`, or `_meta["user.email"]`.
3. If invariant 7 found an existing identity mapping that points elsewhere, fix it in the Flowlines app before the first real calls. Existing sessions are not enriched retroactively.

Then offer to use the Flowlines MCP server to confirm that the deployed integration works. Run the check only when the user accepts.

## Confirm in Flowlines

Use the `flowlines` MCP server that this plugin installs. Follow its conventions: pass `reason` and `user_intent` on each call, and end with its own `report_outcome`, not the one you added to the target server.

1. Traffic. After the deployment is live, ask the user to run one short conversation through a real MCP client that uses the server. Alternatively, when the user authorizes it and the deployed server is reachable, make ten harmless calls that share a test `session.id` and test `user.id`, with a test name/email when supported, then one final `report_outcome` call in the same session. Note the time before the first call and the expected user ID.
2. `get_workspace`: find the namespace that the deployment's API key writes to.
3. `list_sessions` with `from` set to that time, and `user_id` set to the expected user ID when `user.id` is emitted. Sessions normally appear within minutes. If nothing appears, repeat without `user_id`: a session that appears only then has lost its user identity, and no session at all points at the export path.
4. `get_session` on the new session: confirm that it holds every call, `report_outcome` included. Calls spread over several sessions mean that `session.id` is not stable.
5. `get_user_activity` with the expected user ID, and `list_users` (most recently active first by default): confirm that the calls map to that user and, when name and email are sent, that `identity.name` and `identity.email` show them. They need no mapping; when they are missing although the spans carry them, look for a saved mapping that overrides them. Skip this step only when `user.id` is omitted under the no-identity rule, and say so.
6. Ingestion health, quality issues such as `missing_session_identity`, and successful versus unknown call status appear on the MCP page of the Flowlines app, not over MCP. Ask the user to read them there.

Report what each step confirmed, what the user read in the app, and what remains unverified. Behavioral clustering and tool-loop signals have separate volume and timing thresholds, so do not treat their immediate absence as exporter failure.

Verifying receipt and user identity needs the Flowlines MCP server signed in. If authentication is required, or a generic MCP error (such as `-32603`) repeats on one read-only check, use `flowlines-doctor` for connection recovery. Client diagnostics and native sign-in are allowed for this repair; resume receipt verification after tool access is restored.

If the connection remains unavailable, tell the user to check the new session and its user's name and email in the Flowlines app, and say that receipt was not verified. Do not open the app, drive a browser, or search the web to verify it yourself unless the user explicitly asks.
