# Flowlines plugins

Official [Flowlines](https://flowlines.ai) plugins for MCP observability. This repository ships the portable `flowlines` plugin, marketplaces for **Claude Code** and **Codex**, and a **Cursor** plugin manifest (`plugins/flowlines/.cursor-plugin/plugin.json`). Packaging does not by itself establish a public marketplace listing.

**Start here:** [install and sign in](#install), then ask **“Onboard my MCP server to Flowlines.”** Review the plan, approve the changes, and ask **“Check my Flowlines onboarding and fix anything missing.”** See the [four onboarding steps](#onboard-your-mcp-server) or the [website setup guide](https://flowlines.ai/docs).

| Component | What it does |
|---|---|
| `flowlines` MCP server | Connects your MCP client to your Flowlines workspace at `https://api.flowlines.ai/mcp`. Inspect how people use your MCP servers, what changed since a release, and where sessions go wrong. Record findings as notes. Its `onboarding` tool returns an instrumentation plan; `check_onboarding` checks the telemetry that arrives. |
| `flowlines-weekly-review` skill | A periodic review over the MCP server: what changed since the last review, signals, outcome movements, and what to pin for next time. |
| `flowlines-release-check` skill | Before-and-after comparison of an MCP server release: outcomes, intents, cost, signals, and evidence sessions, with the right denominators. |
| `flowlines-investigate-session` skill | From a signal, a user, or a complaint to the failing turn, with minimal exposure of end-user content. |
| `flowlines-cohort-builder` skill | Sizes a user segment, writes it in the Flowlines cohort rule vocabulary, and compares it against a baseline. |
| `flowlines-doctor` skill | Diagnoses missing or incomplete data across every source: instrumented MCP servers, LangSmith and Langfuse connectors, and OTLP applications. |

## Privacy notice

- The Flowlines MCP server reads production MCP sessions, tool calls, and user activity. Treat everything it returns as confidential; it never writes to your namespace except through the explicit `save_note` and `report_outcome` tools.
- An MCP server instrumented from the `onboarding` plan exports validated tool arguments, client-visible results, and user identity metadata to Flowlines. That data can contain personal data, customer data, source code, or other sensitive content. You choose what it records on the Flowlines get-started page.

`onboarding` and `check_onboarding` are read-only: they return an instrumentation plan and check the calls that arrive. The namespace API key is created on the Flowlines get-started page and shown once there; never paste it into chat.

## Install

### ChatGPT and Codex public plugin

[Flowlines is listed in OpenAI's Plugins Directory](https://chatgpt.com/plugins/plugin_asdk_app_6aa11dfaeb20819187226d4810e1d94a).
As of 2026-10-19, the updated plugin has been submitted and is awaiting OpenAI
approval. The live listing can still show the previous prompts and skills until
that update is approved and published. A repository merge does not publish the
directory update or migrate existing installations.

Install the public plugin and connect your Flowlines account when prompted.
Availability and sign-in reuse across ChatGPT and Codex surfaces still need
client-specific verification. The GitHub marketplace commands below install
the repository package. See the [shared plugin guide](docs/chatgpt.md) and
[submission worksheet](docs/openai-submission.md) for maintainer checks.

### Claude Code

```sh
claude plugin marketplace add flowlines-ai/plugins && claude plugin install flowlines@flowlines
```

Then run `/mcp` inside Claude Code and sign in to `flowlines`. Skills are available as `/flowlines:<skill-name>`, for example `/flowlines:flowlines-weekly-review` or `/flowlines:flowlines-doctor`. Add `--scope project` to the install command to enable the plugin for one repository only.

### Local desktop testing

Open this repository in the ChatGPT desktop app and restart the app after
package changes. In the Plugins Directory, select the **Flowlines** marketplace
and install `flowlines`. The repo catalog at `.agents/plugins/marketplace.json`
points to `plugins/flowlines`. Complete the MCP sign-in and test in a new chat.
Local marketplace support can vary by surface; this does not publish the plugin.

### Codex CLI

```sh
codex plugin marketplace add flowlines-ai/plugins && codex plugin add flowlines@flowlines
```

Then sign in with `codex mcp login flowlines`, or open `/plugins` inside Codex. Skills are available as `$<skill-name>`, for example `$flowlines-weekly-review` or `$flowlines-doctor`.

The plugin registers an MCP server named `flowlines`. If you previously added the server by hand under the same name, remove that entry to avoid a duplicate.

### Onboard your MCP server

1. **Create your workspace and connect.** If you are new, open [Flowlines get-started](https://app.flowlines.ai/get-started). Install the plugin above, complete OAuth, and open your MCP server repository in your coding assistant. Start a new session if the plugin is not yet available.
2. **Ask to onboard.** Send this message:

   > Onboard my MCP server to Flowlines.

   Your assistant calls the hosted `onboarding` tool, inspects your repository, and prepares the OpenTelemetry instrumentation plan for your namespace. You do not need to invoke a separate instrumentation skill.
3. **Review and approve the plan.** Check the proposed code changes and which data will be exported. Your coding assistant applies the approved changes and runs the test calls. Create any required namespace API key on get-started and store it in your environment or secret manager.
4. **Ask to verify.** Send this message:

   > Check my Flowlines onboarding and fix anything missing.

   Your assistant calls `check_onboarding`, addresses the reported gaps, and checks again. You are done when it verifies the telemetry from your test calls. Follow the plan's deployment instructions and verify again after deployment.

Signing in connects the assistant; it does not instrument your server. The hosted `onboarding` and `check_onboarding` tools return a plan and verification results. Applying the plan requires a coding assistant with access to your repository. In ChatGPT without repository access, use Flowlines to inspect telemetry and prepare the plan, then apply it in your coding assistant.

### MCP connection errors

If Flowlines calls repeatedly return `Internal error` or `-32603` without a reconnect prompt, use `flowlines-doctor` when installed. It checks available client status and relevant local logs before treating the failure as an authentication problem. When OAuth refresh has failed, it uses an available native reconnect action or tells you how to reconnect in your client, then verifies tool access before resuming your request. No access to Flowlines infrastructure or server logs is needed.

Recovery uses the failing client's sign-in flow on Windows, macOS, or Linux. Local CLI sign-in must complete credential storage; hosted connectors use their own connection status. If login succeeds but tool calls still fail, the MCP connection may need to be reloaded. The skill reports the remaining recovery step; it does not restart the app automatically.

The public analysis bundle does not include `flowlines-doctor`. Its analysis skills use the client's native reconnect action for reported authentication problems and direct unresolved failures to Flowlines support.

## Team rollout

Claude Code reads marketplaces and plugins from a repository's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "flowlines": { "source": { "source": "github", "repo": "flowlines-ai/plugins" } }
  },
  "enabledPlugins": { "flowlines@flowlines": true }
}
```

Codex reads a repository-level marketplace from `.agents/plugins/marketplace.json`:

```json
{
  "name": "my-team",
  "interface": { "displayName": "My team" },
  "plugins": [
    {
      "name": "flowlines",
      "source": {
        "source": "git-subdir",
        "url": "https://github.com/flowlines-ai/plugins.git",
        "path": "./plugins/flowlines",
        "ref": "main"
      },
      "policy": { "installation": "INSTALLED_BY_DEFAULT", "authentication": "ON_USE" },
      "category": "Developer Tools"
    }
  ]
}
```

## Remove the old Claude Code and Codex telemetry

Version 0.2.0 removes the `flowlines-agent-observability` skill. If you used it, its settings stay on your machine and continue to send full prompts, assistant messages, and tool content to Flowlines. The plugin no longer ships its `uninstall.sh`, so remove the settings manually:

1. **Claude Code.** In `~/.claude/settings.json`, delete these keys from `env`: `CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`, `OTEL_LOGS_EXPORTER`, `OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_ASSISTANT_RESPONSES`, `OTEL_LOG_TOOL_DETAILS`, and `OTEL_LOG_TOOL_CONTENT`.
2. **Codex CLI.** In `~/.codex/config.toml`, delete `environment`, `log_user_prompt`, and the `exporter` that contains `x-flowlines-api-key` from `[otel]`. Delete `hooks = true` from `[features]` only if you use no other Codex hooks. In `~/.codex/hooks.json`, delete the `UserPromptSubmit`, `PostToolUse`, and `Stop` entries whose command is `"$HOME/.local/lib/flowlines-agent-observability/codex-hook-relay.sh"`.
3. **Hook relay.** Delete `~/.local/lib/flowlines-agent-observability/`.
4. **State and backups.** `${XDG_CONFIG_HOME:-~/.config}/flowlines-agent-observability/` holds copies of your original configuration files in `originals/`, a `curl.conf` that contains your API key, and a `spool/` of unsent Codex events that can contain prompt content. If you had your own OpenTelemetry settings before the install, restore them from `originals/`. Then delete the folder.
5. **API key.** If you used the key only for this telemetry, revoke it in the Flowlines app under Settings, API keys.

Start new Claude Code and Codex sessions to apply the changes.

## Repository layout

```
.claude-plugin/marketplace.json     Claude Code marketplace
.agents/plugins/marketplace.json    Codex marketplace
plugins/flowlines/
  plugin.json                       Portable identity and OpenAI listing metadata
  mcp.json                          Portable MCP server (streamable-http)
  .claude-plugin/plugin.json        Claude Code manifest
  .codex-plugin/plugin.json         Codex compatibility manifest
  .mcp.json                         Compatibility MCP server (http)
  assets/                           Shared icons
  skills/                           Shared skills
```

The portable package follows [OpenAI's packaging guide](https://developers.openai.com/plugins/build/plugins).
Hosts discover `skills/` and `mcp.json` at the plugin root. OpenAI listing fields
live under `extensions.com.openai.interface` in `plugin.json`. That extension
replaces the compatibility overlay; the two are not merged. Keep identity,
listing fields, versions, and MCP endpoints in sync with the compatibility files.
The tests check these values. Existing clients can still use their original
manifests and `.mcp.json`.

## Development

Validate the manifests with the real CLIs, then the skill packages:

```sh
scripts/validate_plugins.sh
python3 scripts/validate_skills.py
python3 -m unittest discover -s scripts -p 'test_public_submission.py'
```

`validate_plugins.sh` needs `claude` and `codex` on your `PATH`. It runs offline:
Claude validates the manifests, and Codex installs the public bundle and repo
plugin separately in a temporary home. Each install must register exactly one
MCP server at `https://api.flowlines.ai/mcp`. These checks do not complete OAuth
or call the server.

To try the plugin from a checkout without installing it, run `claude --plugin-dir plugins/flowlines`, or add this directory as a local marketplace with `codex plugin marketplace add .`.

## Releasing

Plugin 0.5.0 uses the `onboarding` and `check_onboarding` tools from MCP server 2.0.0.
Deploy that server version before releasing this plugin. The old `onboard` tool is retired;
the user-invoked MCP prompt named `onboard` remains available.

1. Bump `version` in `plugins/flowlines/plugin.json`, `plugins/flowlines/.claude-plugin/plugin.json`, `plugins/flowlines/.codex-plugin/plugin.json`, and the plugin entry in `.claude-plugin/marketplace.json`.
2. Merge to `main`. Marketplace installs track `main`; users pick up the new version with `claude plugin update flowlines@flowlines` or `codex plugin marketplace upgrade`.
3. Tag the release with `claude plugin tag plugins/flowlines`.

Public Plugins Directory releases use the separate
[submission and publication process](docs/openai-submission.md). A repository
merge or tag does not publish that listing.

## History

The skills were moved here from [`flowlines-ai/mcp-server-observability`](https://github.com/flowlines-ai/mcp-server-observability) and [`flowlines-ai/coding-assistant-observability`](https://github.com/flowlines-ai/coding-assistant-observability).

## Support

Questions or issues: [support@flowlines.ai](mailto:support@flowlines.ai), or open an issue in this repository.

## License

MIT
