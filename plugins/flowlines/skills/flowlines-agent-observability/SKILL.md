---
name: flowlines-agent-observability
description: Install, repair, diagnose, or uninstall user-global Flowlines telemetry for Claude Code CLI, Codex CLI, or both on macOS and Linux. Use when a user wants interactive and non-interactive agent sessions exported with full prompts, assistant responses, tool activity, and token usage.
---

# Flowlines Agent Observability

Install a fail-open, user-global integration for every Claude Code and Codex CLI invocation, including `claude -p` and `codex exec`.

## Safety requirements

Before installing or repairing:

1. Explain that full prompts, assistant messages, tool inputs, and tool outputs will leave the machine and be sent to Flowlines.
2. Obtain explicit consent. Never infer consent from a generic telemetry request.
3. Confirm the user has a Flowlines namespace API key. If they do not, tell them to create one in the Flowlines app under Settings, API keys, at `https://app.flowlines.ai/settings` for the namespace that should receive the sessions, and offer to open that page for them (`open` on macOS, `xdg-open` on Linux). The key is shown once at creation.
4. Prefer the installer's masked terminal prompt or a user-created `FLOWLINES_API_KEY_FILE`. If the user wants to provide the key in chat, first warn that it may remain in conversation history and obtain their explicit approval.
5. After a key appears in chat, never repeat, inspect, log, or echo it. Do not place it in a command, environment assignment, temporary file, plan, commentary, or final response.
6. Pass a chat-supplied key only to the masked `/dev/tty` prompt of `scripts/install.sh` through an interactive PTY. If the execution environment cannot send private input to a running PTY without rendering it, use the masked user-terminal or key-file flow instead.
7. Stop on Windows; v1 supports macOS and Linux only.

Read [references/configuration.md](references/configuration.md) before manually changing either agent's config.

## Install or repair

Run:

```sh
scripts/install.sh --target auto
scripts/doctor.sh
```

`auto` detects Claude, Codex, or both. Use `--target claude`, `--target codex`, or `--target both` only when the user explicitly asks. A rerun is an idempotent repair that also folds edits the user made since the last install into the backup.

The installer checks every requested target before changing anything, so a refusal never leaves one agent configured and the other not. If a config already routes OpenTelemetry signals elsewhere (signal-specific `OTEL_EXPORTER_OTLP_*` entries in Claude settings, or a Codex `[otel]` exporter that is not Flowlines), the installer stops and names the entries: keeping them would send full content and the Flowlines key to that collector, and Codex supports one exporter. Ask the user whether to replace them, then rerun with `--replace-existing-otel`; the removed entries stay in the backup and return on uninstall.

For a chat-supplied key, start the installer in an interactive PTY, wait until it prints
`Flowlines API key:`, and send the key followed by a newline to that running PTY. Do not
interpolate it into the shell command or export it as an environment variable. The installer
disables terminal echo before reading it.

The installer:

- backs up original config before its first change;
- merges unrelated Claude settings, Codex TOML, and Codex hooks;
- stores secret-bearing files with mode `0600`;
- configures Claude's logs and enhanced traces against the Flowlines base OTLP endpoint;
- configures Codex logs against `/v1/logs`;
- installs `UserPromptSubmit`, `PostToolUse`, and `Stop` hooks using a bounded, retrying, fail-open relay;
- writes no secret to terminal output.

After a Codex install, tell the user to open `/hooks` once and trust the installed user hook definition. Codex currently skips new non-managed hooks until reviewed. This trust step is required before both interactive Codex and unattended `codex exec` can emit full hook content. Do not suggest `--dangerously-bypass-hook-trust` as a permanent setup.

Then ask the user to run one harmless prompt with each installed CLI and rerun `scripts/doctor.sh`. A successful doctor validates local configuration; receipt in Flowlines validates the end-to-end path.

## Diagnose

Run:

```sh
scripts/doctor.sh
```

Report each failed check without showing secret-bearing file contents. For a repair, rerun `scripts/install.sh --target auto`; it preserves the first-install backup.

If OTel logs arrive but Codex prompt, tool, or final-response content is missing, check `/hooks` trust first. If hook events spool but do not arrive, check network access to the configured Flowlines API and rerun a Codex turn; each hook invocation retries pending events.

## Uninstall

Warn that uninstall removes the local spool, which may contain unsent prompt or tool content. Then run:

```sh
scripts/uninstall.sh
```

Uninstall restores the pre-install versions of managed config files when nothing else changed. If a managed file was edited after installation, it keeps those edits and removes only the Flowlines entries, restoring any values or exporters the installer had replaced.

## Verification

For Skill development, run:

```sh
scripts/test_installer.sh
python3 /path/to/skill-creator/scripts/quick_validate.py .
```

The test uses an isolated temporary home and never contacts Flowlines.
