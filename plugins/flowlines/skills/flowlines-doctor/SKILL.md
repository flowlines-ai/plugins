---
name: flowlines-doctor
description: Diagnose missing or incomplete Flowlines data and failed MCP connections using local checks and the Flowlines MCP server. Covers coding-agent telemetry, instrumented MCP servers, LangSmith and Langfuse connectors, and SDK OTLP. Use when sessions are missing, analysis is stuck, users are unidentified, or MCP calls fail or require sign-in. Do not use to analyse data that is arriving; the Flowlines analysis skills cover that.
---

# Flowlines doctor

Work from the source towards Flowlines and stop at the first broken link. Each check states what it proves, so a green result is not mistaken for "everything works".

## Tool discipline

- Start with local checks (shell commands on this machine) and the Flowlines MCP server. They answer most questions and every step below is written for them.
- Some facts live only in the Flowlines app: MCP ingestion health, connector status, the paused-server toggle, identity mappings. When a check needs one of them, read it in the app if a signed-in browser session is available, or ask the user to read it; say which you did. Do not open the app for anything the MCP server exposes, and do not search the web unless a fact is blocking the diagnosis.
- Match the effort to the question. If the user asks one thing, for example whether sessions arrived in the last hour, make the one or two calls that answer it and stop. Run the full source-by-source procedure only when the user asks for a diagnosis, or when the quick check fails.

## Conventions

- Flowlines MCP tools take `reason` and `user_intent`; keep `user_intent` identical, for example "Find out why Codex sessions stopped appearing in Flowlines".
- Never print, echo, or paste a Flowlines API key. Reachability checks below work without one, and checks that need one read it from a file the user created.
- End with `report_outcome` as the last Flowlines tool call, listing what could not be checked.

## Restore the Flowlines MCP connection first

Use this section when authentication is required, the client cannot start the Flowlines MCP server, or generic MCP failures prevent analysis. Keep the original request, namespace, range, and `user_intent`; connection recovery is a prerequisite, not a new analysis.

### Identify the failure before signing in

- A sign-in prompt or an explicit authentication error such as `401`, `unauthorized`, `invalid_token`, or `login required` is enough to start the bounded sign-in procedure below.
- For a generic error such as `-32603: Internal error`, make at most one read-only check, such as `get_workspace`. Count a check already made by the calling skill; do not repeat it here or try a sequence of account, organization, and namespace calls. Do not retry writes to diagnose a connection.
- If the error repeats, check the MCP connection status and local client logs only when the user's environment exposes them. Match the failing connection and current failure time. Do not access Flowlines source code, infrastructure, deployments, or server logs; unresolved service failures go to Flowlines support.
- Evidence such as `failed to refresh OAuth tokens for server flowlines`, or an OAuth refresh error stating `Failed to parse server response`, supports a fresh sign-in. A missing reconnect prompt or `failureReason=null` does not rule out an authentication problem. An old error, an error for another server, or `-32603` alone is not sufficient evidence.
- Read only the relevant diagnostic entries and quote the minimum non-sensitive error. Never expose tokens, cookies, authorization URLs, or full logs. If local status and logs are unavailable, say which diagnostic is missing; do not invent an authentication cause. Without authentication evidence, report the observed connection error and continue only the checks that it supports.

### Make one bounded sign-in attempt

1. Use the failing client's dedicated MCP or plugin sign-in/reconnect action first. For a local Codex MCP connection, use `codex mcp login flowlines` only when the shell uses the same host, OS user, and client configuration as the failing connection. In Claude Code, use `/mcp`, select `flowlines`, and authenticate. A local CLI login does not repair a separate hosted connector; use that connector's reconnect action. If the action is not exposed to the agent, give the user the reconnect step in their client and wait for completion.
2. Before a shell login, check whether the environment supports browser sign-in and access to the client's configured credential store. For an explicit sandbox permission failure, use the client's normal approval mechanism for that command, with the same OS user and client configuration. Do not use `sudo` or another account, disable the sandbox globally, change credential storage settings, or read saved tokens.
3. If sign-in returns an authorization URL but does not launch it, use an available native URL opener on the user's client host: `open` on macOS, `Start-Process -FilePath` in Windows PowerShell, or `xdg-open` in a Linux desktop session. Pass the exact URL as one safely quoted argument. Do not assume a remote shell, WSL, container, or headless session has access to the user's browser or OAuth callback. When it does not, use the client's supported remote sign-in flow or ask the user to reconnect from their client; do not change callback settings or create a tunnel. Do not search for a login page, alter the URL, or paste an authorization URL containing state or codes into chat or the final report.
4. Ask the user to complete any password, passkey, MFA, or consent step in the browser. Never request credentials or tokens, inspect password fields, enter secrets, complete MFA, or approve permissions on the user's behalf. Do not drive the browser or use computer-use to advance the sign-in, unless the user explicitly asks you to.
5. Confirm that the client reports a completed login, including credential storage for a local CLI. A browser callback followed by `failed to write OAuth tokens to keyring` is not a completed login. A locked or unavailable credential store is not necessarily a sandbox permission problem. Allow one additional login attempt only after the reported storage problem is resolved; otherwise stop and give the user the relevant client or OS repair step. For hosted connectors, rely on the client's reported connection status and the read-only verification below; do not inspect local credentials.

### Verify and resume

After the client reports a completed login, retry one read-only Flowlines call such as `get_workspace`. If it succeeds, resume the original request. A successful login alone does not prove MCP tool access is restored.

If the same connection failure persists, use an available native action to reload that MCP connection once, then make one final read-only check. If reload is unavailable or verification still fails, stop. State what the client confirmed and that tool access remains unverified, name the error, and give the client-specific reconnect or restart step. Do not restart the whole app automatically or interrupt other work. A persistent `403` calls for checking account access to the workspace, not another login.

When connection checks remain blocked, record what could not be checked. Do not repeat `report_outcome` after the same connection failure. Do not present unavailable namespace data as empty data.

## Step 1: what should be arriving

Ask which sources the namespace expects, or infer them:

- `get_workspace` lists every namespace with its ingestion status; pick the namespace and note whether it has ever received data.
- `get_context` returns the activity overview and the agent glossary; `list_agents` shows what has actually been observed. An expected agent that is absent from `list_agents` has never been ingested under that name.
- `list_sessions` with `from` set to the last hour or day shows whether anything is arriving right now. `from` filters on session start time, not ingestion time, so it suits live sources; imported history keeps its original dates. Sessions normally appear within minutes; analysis follows later.

Record the expected sources before checking any of them.

## Step 2: check each source

Full procedures per source are in [references/checks.md](references/checks.md). In short:

- **Claude Code or Codex telemetry.** Run the `doctor.sh` script installed by the `flowlines-agent-observability` skill; it validates local configuration only. Then run one harmless prompt and look for the session with `list_sessions` filtered to the last few minutes. For Codex, hooks must be trusted in `/hooks` before prompt and tool content arrive, and pending events sit in the local spool.
- **An instrumented MCP server.** Confirm the OTLP environment variables are set in the deployment, run ten tool calls plus `report_outcome`, then verify arrival over MCP: `list_agents` for the server's service name and `list_sessions` with `from` set a few minutes back. The ingestion health status (five values) is shown only on the MCP page of the Flowlines app, and the MCP server does not expose it or per-tool failure counts; read it there or ask the user to, and say what each status implicates, from the reference. A paused server under Settings, MCP stops derived observability without stopping ingestion.
- **LangSmith or Langfuse connectors.** Status lives under Settings, Connectors in the app and is not exposed over MCP: `disconnected`, `configured`, `invalidCredentials`, `syncing`, or `paused`, with the last validation and sync times. Read it there or ask the user to; validation and sync are the user's actions. Then verify arrival over MCP across the provider's history window, since imported sessions keep their original dates.
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
