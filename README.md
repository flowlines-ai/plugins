# Flowlines plugins

Official [Flowlines](https://flowlines.ai) plugins for MCP observability. This repository ships the portable `flowlines` plugin, marketplaces for **Claude Code** and **Codex**, and a **Cursor** plugin manifest (`plugins/flowlines/.cursor-plugin/plugin.json`) for [cursor.directory](https://cursor.directory/plugins):

| Component | What it does |
|---|---|
| `flowlines` MCP server | Connects your MCP client to your Flowlines workspace at `https://api.flowlines.ai/mcp`. Inspect how people use your MCP servers, what changed since a release, and where sessions go wrong. Record findings as notes. Its `onboarding` tool returns an instrumentation plan; `check_onboarding` checks the telemetry that arrives. |

## Privacy notice

- The Flowlines MCP server reads production MCP sessions, tool calls, and user activity. Treat everything it returns as confidential; it never writes to your namespace except through the explicit `save_note` and `report_outcome` tools.
- An MCP server instrumented from the `onboarding` plan exports validated tool arguments, client-visible results, and user identity metadata to Flowlines. That data can contain personal data, customer data, source code, or other sensitive content. You choose what it records on the Flowlines get-started page.

`onboarding` and `check_onboarding` are read-only: they return an instrumentation plan and check the calls that arrive. The namespace API key is created on the Flowlines get-started page and shown once there; never paste it into chat.

## Install

### ChatGPT and Codex public plugin

The public distribution target is one **Flowlines** plugin with the hosted MCP
server in OpenAI's Plugins Directory. This repository prepares its submission;
merging changes does not publish it or install it for users. A public listing
and installation reuse across products still require review and verification.

See the [shared plugin guide](docs/chatgpt.md) for the build and verification
steps, and the [submission worksheet](docs/openai-submission.md) for listing
assets and review cases. The existing desktop marketplace installs below
continue to work. Personal ChatGPT accounts can test the server separately
through Developer mode while the public submission is being prepared.

### Claude Code

```sh
claude plugin marketplace add flowlines-ai/plugins && claude plugin install flowlines@flowlines
```

Then run `/mcp` inside Claude Code and sign in to `flowlines`. Add `--scope project` to the install command to enable the plugin for one repository only.

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

Then sign in with `codex mcp login flowlines`, or open `/plugins` inside Codex.

The plugin registers an MCP server named `flowlines`. If you previously added the server by hand under the same name, remove that entry to avoid a duplicate.

### After you sign in

Signing in also creates your Flowlines account. When you have no workspace or API key yet, the Flowlines get-started page creates them, then turns green on your server's first tool call. To instrument your MCP server, ask your MCP client to onboard you to Flowlines: it calls `onboarding` for your namespace, carries out the plan, and verifies the first calls with `check_onboarding`.

### MCP connection errors

If Flowlines calls repeatedly return `Internal error` or `-32603` without a reconnect prompt, the OAuth refresh may have failed. Sign in again with the failing client's reconnect action: in Claude Code, run `/mcp` and select `flowlines`; in the Codex CLI, run `codex mcp login flowlines`; in a hosted client, use the connector's reconnect action. If sign-in succeeds but tool calls still fail, reload the MCP connection or start a new session.

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
  .cursor-plugin/plugin.json        Cursor manifest
  .mcp.json                         Compatibility MCP server (http)
  assets/                           Shared icons
```

The portable package follows [OpenAI's packaging guide](https://developers.openai.com/plugins/build/plugins).
Hosts discover `mcp.json` at the plugin root. OpenAI listing fields
live under `extensions.com.openai.interface` in `plugin.json`. That extension
replaces the compatibility overlay; the two are not merged. Keep identity,
listing fields, versions, and MCP endpoints in sync with the compatibility files.
The tests check these values. Existing clients can still use their original
manifests and `.mcp.json`.

## Development

Validate the manifests with the real CLIs, then run the unit tests:

```sh
scripts/validate_plugins.sh
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

Plugin 0.6.0 removes the five skills. The plugin now ships only the `flowlines` MCP server.

1. Bump `version` in `plugins/flowlines/plugin.json`, `plugins/flowlines/.claude-plugin/plugin.json`, `plugins/flowlines/.codex-plugin/plugin.json`, `plugins/flowlines/.cursor-plugin/plugin.json`, and the plugin entry in `.claude-plugin/marketplace.json`.
2. Merge to `main`. Marketplace installs track `main`; users pick up the new version with `claude plugin update flowlines@flowlines` or `codex plugin marketplace upgrade`.
3. Tag the release with `claude plugin tag plugins/flowlines`.

Public Plugins Directory releases use the separate
[submission and publication process](docs/openai-submission.md). A repository
merge or tag does not publish that listing.

## Support

Questions or issues: [support@flowlines.ai](mailto:support@flowlines.ai), or open an issue in this repository.

## License

MIT
