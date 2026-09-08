#!/bin/sh
# Validate the marketplace and plugin manifests with the real Claude Code and Codex CLIs.
# Both checks are offline: Claude validates the manifests, Codex installs the plugin from
# this checkout into a throwaway CODEX_HOME and lists the MCP server it registered.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MARKETPLACE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "${ROOT}/.agents/plugins/marketplace.json")

echo "== Claude Code"
claude plugin validate "${ROOT}" --strict
for plugin in "${ROOT}"/plugins/*/; do
  claude plugin validate "${plugin}" --strict
done

echo "== Codex"
CODEX_HOME=$(mktemp -d)
export CODEX_HOME
trap 'rm -rf "${CODEX_HOME}"' EXIT HUP INT TERM

echo "== ChatGPT package"
python3 "${ROOT}/scripts/build_chatgpt_plugin.py" \
  --app-id asdk_app_offline_test --output "${CODEX_HOME}/chatgpt"
codex plugin marketplace add "${CODEX_HOME}/chatgpt" >/dev/null
codex plugin add flowlines-chatgpt@flowlines-chatgpt --json
codex mcp list --json > "${CODEX_HOME}/chatgpt-mcp.json"
python3 -c 'import json,sys; servers=json.load(open(sys.argv[1])); sys.exit("ChatGPT package registered a desktop MCP server") if servers else None' "${CODEX_HOME}/chatgpt-mcp.json"

codex plugin marketplace add "${ROOT}" >/dev/null
for plugin in "${ROOT}"/plugins/*/; do
  name=$(basename "${plugin}")
  codex plugin add "${name}@${MARKETPLACE}" --json
done
codex plugin list
codex mcp list
