#!/bin/sh

set -eu

FLOWLINES_SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FLOWLINES_TEST_ROOT=$(mktemp -d)
trap 'rm -rf "${FLOWLINES_TEST_ROOT}"' EXIT HUP INT TERM

export FLOWLINES_AGENT_HOME="${FLOWLINES_TEST_ROOT}/home"
export FLOWLINES_AGENT_CONFIG_HOME="${FLOWLINES_AGENT_HOME}/.config"
export FLOWLINES_API_KEY="sk-flowlines-test-secret"
export FLOWLINES_FULL_CONTENT_CONSENT=yes
mkdir -p "${FLOWLINES_AGENT_HOME}/.claude" "${FLOWLINES_AGENT_HOME}/.codex"

printf '%s\n' '{"theme":"dark","env":{"KEEP_ME":"yes"}}' > "${FLOWLINES_AGENT_HOME}/.claude/settings.json"
printf '%s\n' 'model = "gpt-test"' > "${FLOWLINES_AGENT_HOME}/.codex/config.toml"
printf '%s\n' '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo existing"}]}]}}' > "${FLOWLINES_AGENT_HOME}/.codex/hooks.json"
cp "${FLOWLINES_AGENT_HOME}/.claude/settings.json" "${FLOWLINES_TEST_ROOT}/claude.original"
cp "${FLOWLINES_AGENT_HOME}/.codex/config.toml" "${FLOWLINES_TEST_ROOT}/codex.original"
cp "${FLOWLINES_AGENT_HOME}/.codex/hooks.json" "${FLOWLINES_TEST_ROOT}/hooks.original"

"${FLOWLINES_SCRIPT_DIR}/install.sh" --target both --non-interactive >/dev/null
"${FLOWLINES_SCRIPT_DIR}/doctor.sh" >/dev/null

python3 - <<'PY'
import json
import os
import re
from pathlib import Path

home = Path(os.environ["FLOWLINES_AGENT_HOME"])
claude = json.loads((home / ".claude/settings.json").read_text())
assert claude["theme"] == "dark"
assert claude["env"]["KEEP_ME"] == "yes"
assert claude["env"]["OTEL_LOG_TOOL_CONTENT"] == "1"
assert "sk-flowlines-test-secret" in claude["env"]["OTEL_EXPORTER_OTLP_HEADERS"]

codex = (home / ".codex/config.toml").read_text()
assert 'model = "gpt-test"' in codex
assert re.search(r"(?ms)^\[otel\].*^log_user_prompt = true$", codex)
assert re.search(r"(?ms)^\[features\].*^hooks = true$", codex)

hooks = json.loads((home / ".codex/hooks.json").read_text())["hooks"]
assert len(hooks["UserPromptSubmit"]) == 1
assert len(hooks["PostToolUse"]) == 1
assert len(hooks["Stop"]) == 2
PY

FLOWLINES_FIRST_HASH=$(python3 - <<'PY'
import hashlib
import os
from pathlib import Path

home = Path(os.environ["FLOWLINES_AGENT_HOME"])
digest = hashlib.sha256()
for path in (home / ".claude/settings.json", home / ".codex/config.toml", home / ".codex/hooks.json"):
    digest.update(path.read_bytes())
print(digest.hexdigest())
PY
)
"${FLOWLINES_SCRIPT_DIR}/install.sh" --target both --non-interactive >/dev/null
FLOWLINES_SECOND_HASH=$(python3 - <<'PY'
import hashlib
import os
from pathlib import Path

home = Path(os.environ["FLOWLINES_AGENT_HOME"])
digest = hashlib.sha256()
for path in (home / ".claude/settings.json", home / ".codex/config.toml", home / ".codex/hooks.json"):
    digest.update(path.read_bytes())
print(digest.hexdigest())
PY
)
[ "${FLOWLINES_FIRST_HASH}" = "${FLOWLINES_SECOND_HASH}" ]

for FLOWLINES_PRIVATE_FILE in \
  "${FLOWLINES_AGENT_HOME}/.claude/settings.json" \
  "${FLOWLINES_AGENT_HOME}/.codex/config.toml" \
  "${FLOWLINES_AGENT_HOME}/.codex/hooks.json" \
  "${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability/curl.conf" \
  "${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability/state.json" \
  "${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability/originals/claude.original" \
  "${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability/originals/codex.original" \
  "${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability/originals/hooks.original"
do
  case "$(uname -s)" in
    Darwin) FLOWLINES_MODE=$(stat -f '%Lp' "${FLOWLINES_PRIVATE_FILE}") ;;
    Linux) FLOWLINES_MODE=$(stat -c '%a' "${FLOWLINES_PRIVATE_FILE}") ;;
    *) printf '%s\n' "Unsupported test platform." >&2; exit 1 ;;
  esac
  [ "${FLOWLINES_MODE}" = "600" ]
done

mkdir -p "${FLOWLINES_TEST_ROOT}/bin"
printf '%s\n' '#!/bin/sh' 'exit 1' > "${FLOWLINES_TEST_ROOT}/bin/curl"
chmod 700 "${FLOWLINES_TEST_ROOT}/bin/curl"
FLOWLINES_RELAY="${FLOWLINES_AGENT_HOME}/.local/lib/flowlines-agent-observability/codex-hook-relay.sh"
FLOWLINES_OUTPUT=$(printf '%s' '{"hook_event_name":"Stop"}' | PATH="${FLOWLINES_TEST_ROOT}/bin:${PATH}" "${FLOWLINES_RELAY}")
[ "${FLOWLINES_OUTPUT}" = "{}" ]
find "${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability/spool" -name '*.json' -type f | grep -q .

export FLOWLINES_TEST_CURL_ARGS="${FLOWLINES_TEST_ROOT}/curl.args"
printf '%s\n' \
  '#!/bin/sh' \
  'printf "%s\n" "$@" > "${FLOWLINES_TEST_CURL_ARGS}"' \
  'printf "200"' \
  'exit 0' > "${FLOWLINES_TEST_ROOT}/bin/curl"
FLOWLINES_OUTPUT=$(printf '%s' '{"hook_event_name":"Stop"}' | PATH="${FLOWLINES_TEST_ROOT}/bin:${PATH}" "${FLOWLINES_RELAY}")
[ "${FLOWLINES_OUTPUT}" = "{}" ]
grep -q 'x-flowlines-event-time-unix:' "${FLOWLINES_TEST_CURL_ARGS}"

# A pipe may return short reads, so exercise a payload larger than a typical pipe buffer.
printf '%s\n' \
  '#!/bin/sh' \
  'printf "000"' \
  'exit 7' > "${FLOWLINES_TEST_ROOT}/bin/curl"
export FLOWLINES_LARGE_BYTES=1048576
FLOWLINES_OUTPUT=$(
  python3 -c 'import os, sys; sys.stdout.write("x" * int(os.environ["FLOWLINES_LARGE_BYTES"]))' |
    PATH="${FLOWLINES_TEST_ROOT}/bin:${PATH}" "${FLOWLINES_RELAY}"
)
[ "${FLOWLINES_OUTPUT}" = "{}" ]
FLOWLINES_LARGE_SPOOL=$(find "${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability/spool" -name '*.json' -type f -size "${FLOWLINES_LARGE_BYTES}c" -print -quit)
[ -n "${FLOWLINES_LARGE_SPOOL}" ]

# Permanent client failures are discarded so they cannot starve newer events.
printf '%s\n' \
  '#!/bin/sh' \
  'printf "400"' \
  'exit 22' > "${FLOWLINES_TEST_ROOT}/bin/curl"
FLOWLINES_OUTPUT=$(printf '%s' '{"hook_event_name":"Stop"}' | PATH="${FLOWLINES_TEST_ROOT}/bin:${PATH}" "${FLOWLINES_RELAY}")
[ "${FLOWLINES_OUTPUT}" = "{}" ]
[ -z "$(find "${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability/spool" -name '*.json' -type f -print -quit)" ]

# Server and network failures remain queued for a later retry.
printf '%s\n' \
  '#!/bin/sh' \
  'printf "503"' \
  'exit 22' > "${FLOWLINES_TEST_ROOT}/bin/curl"
FLOWLINES_OUTPUT=$(printf '%s' '{"hook_event_name":"Stop"}' | PATH="${FLOWLINES_TEST_ROOT}/bin:${PATH}" "${FLOWLINES_RELAY}")
[ "${FLOWLINES_OUTPUT}" = "{}" ]
find "${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability/spool" -name '*.json' -type f | grep -q .

"${FLOWLINES_SCRIPT_DIR}/uninstall.sh" >/dev/null
cmp "${FLOWLINES_AGENT_HOME}/.claude/settings.json" "${FLOWLINES_TEST_ROOT}/claude.original"
cmp "${FLOWLINES_AGENT_HOME}/.codex/config.toml" "${FLOWLINES_TEST_ROOT}/codex.original"
cmp "${FLOWLINES_AGENT_HOME}/.codex/hooks.json" "${FLOWLINES_TEST_ROOT}/hooks.original"
[ ! -e "${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability" ]

export FLOWLINES_AGENT_HOME="${FLOWLINES_TEST_ROOT}/clean-home"
export FLOWLINES_AGENT_CONFIG_HOME="${FLOWLINES_AGENT_HOME}/.config"
"${FLOWLINES_SCRIPT_DIR}/install.sh" --target both --non-interactive >/dev/null
"${FLOWLINES_SCRIPT_DIR}/doctor.sh" >/dev/null
"${FLOWLINES_SCRIPT_DIR}/uninstall.sh" >/dev/null
[ ! -e "${FLOWLINES_AGENT_HOME}/.claude/settings.json" ]
[ ! -e "${FLOWLINES_AGENT_HOME}/.codex/config.toml" ]
[ ! -e "${FLOWLINES_AGENT_HOME}/.codex/hooks.json" ]
[ ! -e "${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability" ]
[ ! -e "${FLOWLINES_AGENT_HOME}/.local/lib/flowlines-agent-observability" ]

printf '%s\n' "Installer tests passed."
