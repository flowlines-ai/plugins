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
validation_home=$(mktemp -d)
trap 'rm -rf "${validation_home}"' EXIT HUP INT TERM
codex_check() {
  env CODEX_HOME="${validation_home}" codex "$@"
}
check_mcp() {
  codex_check mcp list --json > "${validation_home}/mcp.json"
  python3 - "${validation_home}/mcp.json" <<'PY'
import json
import sys

servers = json.load(open(sys.argv[1]))
if len(servers) != 1 or servers[0]["transport"].get("url") != "https://api.flowlines.ai/mcp":
    sys.exit("Expected exactly one Flowlines MCP server at https://api.flowlines.ai/mcp")
PY
}

echo "== Public submission assets"
python3 "${ROOT}/scripts/build_public_submission.py" --output "${validation_home}/submission"
# This catalog exists only in the disposable test home, not in the release ZIP.
python3 - "${validation_home}/submission" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]) / ".agents/plugins/marketplace.json"
path.parent.mkdir(parents=True)
path.write_text(json.dumps({
    "name": "flowlines-submission-check",
    "plugins": [{
        "name": "flowlines",
        "source": {"source": "local", "path": "./flowlines"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Developer Tools",
    }],
}))
PY
codex_check plugin marketplace add "${validation_home}/submission" >/dev/null
codex_check plugin add flowlines@flowlines-submission-check --json
check_mcp
codex_check plugin remove flowlines@flowlines-submission-check >/dev/null

codex_check plugin marketplace add "${ROOT}" >/dev/null
for plugin in "${ROOT}"/plugins/*/; do
  name=$(basename "${plugin}")
  codex_check plugin add "${name}@${MARKETPLACE}" --json
done
check_mcp
codex_check plugin list
codex_check mcp list
