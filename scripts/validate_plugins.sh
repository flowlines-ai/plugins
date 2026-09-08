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

echo "== Public submission assets"
python3 "${ROOT}/scripts/build_public_submission.py" --output "${CODEX_HOME}/submission"
# This catalog exists only in the disposable test home, not in the release ZIP.
python3 - "${CODEX_HOME}/submission" <<'PY'
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
codex plugin marketplace add "${CODEX_HOME}/submission" >/dev/null
codex plugin add flowlines@flowlines-submission-check --json
codex mcp list --json > "${CODEX_HOME}/submission-mcp.json"
python3 -c 'import json,sys; servers=json.load(open(sys.argv[1])); sys.exit("Submission assets registered a desktop MCP server") if servers else None' "${CODEX_HOME}/submission-mcp.json"

codex plugin marketplace add "${ROOT}" >/dev/null
for plugin in "${ROOT}"/plugins/*/; do
  name=$(basename "${plugin}")
  codex plugin add "${name}@${MARKETPLACE}" --json
done
codex plugin list
codex mcp list
