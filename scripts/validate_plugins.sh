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
codex plugin marketplace add "${ROOT}" >/dev/null
for plugin in "${ROOT}"/plugins/*/; do
  name=$(basename "${plugin}")
  codex plugin add "${name}@${MARKETPLACE}" --json
done
codex plugin list
codex mcp list
