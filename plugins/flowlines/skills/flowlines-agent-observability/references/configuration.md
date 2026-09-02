# Flowlines agent configuration reference

The production Flowlines API base URL is `https://api.flowlines.ai`.

## Claude Code

Merge these entries into the `env` object in `~/.claude/settings.json`:

```json
{
  "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
  "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
  "OTEL_LOGS_EXPORTER": "otlp",
  "OTEL_TRACES_EXPORTER": "otlp",
  "OTEL_METRICS_EXPORTER": "none",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://api.flowlines.ai",
  "OTEL_EXPORTER_OTLP_HEADERS": "x-flowlines-api-key=<secret>",
  "OTEL_LOG_USER_PROMPTS": "1",
  "OTEL_LOG_ASSISTANT_RESPONSES": "1",
  "OTEL_LOG_TOOL_DETAILS": "1",
  "OTEL_LOG_TOOL_CONTENT": "1"
}
```

The base endpoint is intentional: the OTLP exporter resolves `/v1/logs` and `/v1/traces`. These user-global environment settings apply to interactive Claude Code and `claude -p`.

## Codex

Merge this table into `~/.codex/config.toml`:

```toml
[otel]
environment = "production"
log_user_prompt = true
exporter = { otlp-http = { endpoint = "https://api.flowlines.ai/v1/logs", protocol = "binary", headers = { "x-flowlines-api-key" = "<secret>" } } }
```

Keep other `[otel]` keys, including a trace or metrics exporter, unchanged. User-level telemetry applies to interactive Codex and `codex exec`.

Merge three command hooks into `~/.codex/hooks.json`:

- `UserPromptSubmit` provides `session_id`, `turn_id`, and `prompt`.
- `PostToolUse` provides `session_id`, `turn_id`, `tool_name`, `tool_use_id`, `tool_input`, and `tool_response`.
- `Stop` provides `session_id`, `turn_id`, and `last_assistant_message`.

All three invoke the installed `codex-hook-relay.sh`. The relay must always write valid `{}` to stdout and exit zero. Codex requires the user to review and trust new non-managed hooks through `/hooks`.

The relay reads at most 8 MiB per event, preserves the original capture time in
`x-flowlines-event-time-unix`, and retries pending network and server failures. Permanent
HTTP 4xx responses are discarded so a malformed event cannot starve newer spool entries.

## Secret and privacy rules

- Full prompt and tool content is deliberately enabled. Obtain explicit consent before changing config.
- Prefer masked terminal or key-file entry. A key provided in chat may remain in conversation
  history; warn the user first, never repeat it, and send it only to the installer's non-echoing
  interactive prompt.
- Never include the Flowlines key in exported prompt, hook, or diagnostic output.
- Apply `0600` to Claude settings, Codex config, the curl config, backups, and installer state.
- Keep the relay spool bounded. Each event is capped at 8 MiB and the spool retains at most 100 events.
- A Flowlines key is an ingestion credential, not an authorization to export unrelated files or environment variables.
