# Flowlines plugins

Official [Flowlines](https://flowlines.ai) plugins for coding agents. One repository serves as a plugin marketplace for both **Claude Code** and **Codex CLI**, and ships the `flowlines` plugin:

| Component | What it does |
|---|---|
| `flowlines` MCP server | Connects your agent to your Flowlines workspace at `https://api.flowlines.ai/mcp`. Ask what your agents' users did, what changed since a release, where sessions go wrong, and record findings as notes. |
| `flowlines-mcp-observability` skill | Instruments an MCP server so its tool calls arrive in Flowlines as canonical MCP telemetry, through AGNTCY Observe or vanilla OpenTelemetry. |
| `flowlines-agent-observability` skill | Installs, repairs, diagnoses, or removes user-level Flowlines telemetry for Claude Code and Codex CLI sessions on macOS and Linux. |

## Privacy notice

- The MCP server reads production conversations between end users and your agents. Treat everything it returns as confidential; it never writes to your namespace except through the explicit `save_note` and `report_outcome` tools.
- `flowlines-mcp-observability` exports validated tool arguments, client-visible results, and user identity metadata from the instrumented server to Flowlines. That data can contain personal data, customer data, source code, or other sensitive content.
- `flowlines-agent-observability` exports full prompts, assistant messages, tool inputs, and tool outputs from your machine to Flowlines.

Both skills ask for explicit consent before changing anything, and neither prints or stores your Flowlines API key in chat. They need a namespace API key, created in the Flowlines app under Settings, API keys; the skills point you there and can open the page for you.

## Install

### Claude Code

```sh
claude plugin marketplace add flowlines-ai/plugins && claude plugin install flowlines@flowlines
```

Then run `/mcp` inside Claude Code and sign in to `flowlines`. Skills are available as `/flowlines:flowlines-mcp-observability` and `/flowlines:flowlines-agent-observability`. Add `--scope project` to the install command to enable the plugin for one repository only.

### Codex CLI

```sh
codex plugin marketplace add flowlines-ai/plugins && codex plugin add flowlines@flowlines
```

Then sign in with `codex mcp login flowlines`, or open `/plugins` inside Codex. Skills are available as `$flowlines-mcp-observability` and `$flowlines-agent-observability`.

The plugin registers an MCP server named `flowlines`. If you previously added the server by hand under the same name, remove that entry to avoid a duplicate.

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
        "path": "plugins/flowlines"
      },
      "policy": { "installation": "INSTALLED_BY_DEFAULT", "authentication": "ON_USE" }
    }
  ]
}
```

## Repository layout

```
.claude-plugin/marketplace.json     Claude Code marketplace
.agents/plugins/marketplace.json    Codex marketplace
plugins/flowlines/
  .claude-plugin/plugin.json        Claude Code manifest
  .codex-plugin/plugin.json         Codex manifest and directory listing
  .mcp.json                         MCP server shared by both clients
  skills/                           Skills shared by both clients
```

Both clients read the same `.mcp.json` and `skills/` tree. Each client keeps its own manifest because Claude Code only reads `.claude-plugin/plugin.json` and Codex adds directory metadata under `interface`.

## Development

Validate the manifests with the real CLIs, then the skill packages and the installer:

```sh
scripts/validate_plugins.sh
python3 scripts/validate_skills.py
plugins/flowlines/skills/flowlines-agent-observability/scripts/test_installer.sh
```

`validate_plugins.sh` needs `claude` and `codex` on your `PATH`. It runs offline: Claude validates the manifests and Codex installs the plugin from this checkout into a throwaway `CODEX_HOME`.

To try the plugin from a checkout without installing it, run `claude --plugin-dir plugins/flowlines`, or add this directory as a local marketplace with `codex plugin marketplace add .`.

## Releasing

1. Bump `version` in `plugins/flowlines/.claude-plugin/plugin.json`, `plugins/flowlines/.codex-plugin/plugin.json`, and the plugin entry in `.claude-plugin/marketplace.json`.
2. Merge to `main`. Marketplace installs track `main`; users pick up the new version with `claude plugin update flowlines@flowlines` or `codex plugin marketplace upgrade`.
3. Tag the release with `claude plugin tag plugins/flowlines`.

## History

The skills were moved here from [`flowlines-ai/mcp-server-observability`](https://github.com/flowlines-ai/mcp-server-observability) and [`flowlines-ai/coding-assistant-observability`](https://github.com/flowlines-ai/coding-assistant-observability).

## Support

Questions or issues: [support@flowlines.ai](mailto:support@flowlines.ai), or open an issue in this repository.

## License

MIT
