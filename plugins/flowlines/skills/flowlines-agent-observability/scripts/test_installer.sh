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

FLOWLINES_STATE="${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability"
FLOWLINES_SPOOL="${FLOWLINES_STATE}/spool"
FLOWLINES_RELAY="${FLOWLINES_AGENT_HOME}/.local/lib/flowlines-agent-observability/codex-hook-relay.sh"

file_mode() {
  case "$(uname -s)" in
    Darwin) stat -f '%Lp' "$1" ;;
    Linux) stat -c '%a' "$1" ;;
    *) printf '%s\n' "Unsupported test platform." >&2; exit 1 ;;
  esac
}

stub_curl() {
  # $1: printed HTTP status, $2: exit code, $3: optional seconds to sleep before answering
  mkdir -p "${FLOWLINES_TEST_ROOT}/bin"
  printf '%s\n' \
    '#!/bin/sh' \
    "[ -n \"${3:-}\" ] && sleep ${3:-0}" \
    'printf "%s\n" "$@" > "${FLOWLINES_TEST_CURL_ARGS}"' \
    'printf "1" >> "${FLOWLINES_TEST_CURL_CALLS}"' \
    "printf \"$1\"" \
    "exit $2" > "${FLOWLINES_TEST_ROOT}/bin/curl"
  chmod 700 "${FLOWLINES_TEST_ROOT}/bin/curl"
  : > "${FLOWLINES_TEST_CURL_CALLS}"
}
export FLOWLINES_TEST_CURL_ARGS="${FLOWLINES_TEST_ROOT}/curl.args"
export FLOWLINES_TEST_CURL_CALLS="${FLOWLINES_TEST_ROOT}/curl.calls"

relay() {
  printf '%s' '{"hook_event_name":"Stop"}' | PATH="${FLOWLINES_TEST_ROOT}/bin:${PATH}" "${FLOWLINES_RELAY}"
}

spool_count() {
  find "${FLOWLINES_SPOOL}" -name '*.json' -type f | wc -l | tr -d ' '
}

# --- baseline install merges into existing files ---------------------------------------------

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

# A repair without other edits leaves every managed file byte-identical.
hash_managed() {
  cat "${FLOWLINES_AGENT_HOME}/.claude/settings.json" "${FLOWLINES_AGENT_HOME}/.codex/config.toml" "${FLOWLINES_AGENT_HOME}/.codex/hooks.json" | cksum
}
FLOWLINES_FIRST_HASH=$(hash_managed)
"${FLOWLINES_SCRIPT_DIR}/install.sh" --target both --non-interactive >/dev/null
[ "${FLOWLINES_FIRST_HASH}" = "$(hash_managed)" ]

for FLOWLINES_PRIVATE_FILE in \
  "${FLOWLINES_AGENT_HOME}/.claude/settings.json" \
  "${FLOWLINES_AGENT_HOME}/.codex/config.toml" \
  "${FLOWLINES_AGENT_HOME}/.codex/hooks.json" \
  "${FLOWLINES_STATE}/curl.conf" \
  "${FLOWLINES_STATE}/state.json" \
  "${FLOWLINES_STATE}/originals/claude.original" \
  "${FLOWLINES_STATE}/originals/codex.original" \
  "${FLOWLINES_STATE}/originals/hooks.original"
do
  [ "$(file_mode "${FLOWLINES_PRIVATE_FILE}")" = "600" ]
done

# --- relay ----------------------------------------------------------------------------------

# Network failure: the event is kept and the hook still answers {}.
stub_curl 000 1
[ "$(relay)" = "{}" ]
[ "$(spool_count)" = "1" ]

# Success drains the spool and preserves the capture time header.
stub_curl 200 0
[ "$(relay)" = "{}" ]
grep -q 'x-flowlines-event-time-unix:' "${FLOWLINES_TEST_CURL_ARGS}"
[ "$(spool_count)" = "0" ]

# A pipe may return short reads, so exercise a payload larger than a typical pipe buffer.
stub_curl 000 7
export FLOWLINES_LARGE_BYTES=1048576
FLOWLINES_OUTPUT=$(
  python3 -c 'import os, sys; sys.stdout.write("x" * int(os.environ["FLOWLINES_LARGE_BYTES"]))' |
    PATH="${FLOWLINES_TEST_ROOT}/bin:${PATH}" "${FLOWLINES_RELAY}"
)
[ "${FLOWLINES_OUTPUT}" = "{}" ]
[ -n "$(find "${FLOWLINES_SPOOL}" -name '*.json' -type f -size "${FLOWLINES_LARGE_BYTES}c" -print -quit)" ]
rm -f "${FLOWLINES_SPOOL}"/*.json

# Permanent client failures are discarded so they cannot starve newer events.
stub_curl 400 22
[ "$(relay)" = "{}" ]
[ "$(spool_count)" = "0" ]

# Rate limiting and request timeouts are retryable, like server and network failures.
for FLOWLINES_RETRYABLE in 429 408 503; do
  stub_curl "${FLOWLINES_RETRYABLE}" 22
  [ "$(relay)" = "{}" ]
  [ "$(spool_count)" = "1" ]
  rm -f "${FLOWLINES_SPOOL}"/*.json
done

# Events still being captured live in dotfiles, which the relay never sends or prunes.
printf '%s' '{"partial":' > "${FLOWLINES_SPOOL}/.incoming-1-1"
stub_curl 200 0
[ "$(relay)" = "{}" ]
[ "$(wc -c < "${FLOWLINES_TEST_CURL_CALLS}" | tr -d ' ')" = "1" ]
[ -f "${FLOWLINES_SPOOL}/.incoming-1-1" ]
rm -f "${FLOWLINES_SPOOL}/.incoming-1-1"

# A slow endpoint with a backlog must not exceed the 5 second hook timeout: the current event
# is sent, then the backlog is skipped once the send budget is spent.
printf '%s' '{"old":1}' > "${FLOWLINES_SPOOL}/1-1.json"
printf '%s' '{"old":2}' > "${FLOWLINES_SPOOL}/1-2.json"
stub_curl 503 22 3
FLOWLINES_BEFORE=$(date +%s)
[ "$(relay)" = "{}" ]
FLOWLINES_ELAPSED=$(( $(date +%s) - FLOWLINES_BEFORE ))
[ "${FLOWLINES_ELAPSED}" -lt 5 ]
[ "$(wc -c < "${FLOWLINES_TEST_CURL_CALLS}" | tr -d ' ')" = "1" ]
[ "$(spool_count)" = "3" ]
rm -f "${FLOWLINES_SPOOL}"/*.json

# --- uninstall restores the pre-install files when nothing else changed ---------------------

"${FLOWLINES_SCRIPT_DIR}/uninstall.sh" >/dev/null
cmp "${FLOWLINES_AGENT_HOME}/.claude/settings.json" "${FLOWLINES_TEST_ROOT}/claude.original"
cmp "${FLOWLINES_AGENT_HOME}/.codex/config.toml" "${FLOWLINES_TEST_ROOT}/codex.original"
cmp "${FLOWLINES_AGENT_HOME}/.codex/hooks.json" "${FLOWLINES_TEST_ROOT}/hooks.original"
[ ! -e "${FLOWLINES_STATE}" ]

# --- edits made after installation survive repair and uninstall -----------------------------

"${FLOWLINES_SCRIPT_DIR}/install.sh" --target both --non-interactive >/dev/null
python3 - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ["FLOWLINES_AGENT_HOME"])
claude_path = home / ".claude/settings.json"
claude = json.loads(claude_path.read_text())
claude["addedLater"] = True
claude["env"]["ADDED_LATER"] = "1"
claude_path.write_text(json.dumps(claude, indent=2) + "\n")

codex_path = home / ".codex/config.toml"
codex_path.write_text(codex_path.read_text() + '\n[custom]\nadded_later = "yes"\n')

hooks_path = home / ".codex/hooks.json"
hooks = json.loads(hooks_path.read_text())
hooks["hooks"]["UserPromptSubmit"].append({"hooks": [{"type": "command", "command": "echo added later"}]})
hooks_path.write_text(json.dumps(hooks, indent=2) + "\n")
PY
"${FLOWLINES_SCRIPT_DIR}/install.sh" --target both --non-interactive >/dev/null
"${FLOWLINES_SCRIPT_DIR}/doctor.sh" >/dev/null
"${FLOWLINES_SCRIPT_DIR}/uninstall.sh" >/dev/null
python3 - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ["FLOWLINES_AGENT_HOME"])
claude = json.loads((home / ".claude/settings.json").read_text())
assert claude["theme"] == "dark" and claude["addedLater"] is True
assert claude["env"] == {"KEEP_ME": "yes", "ADDED_LATER": "1"}, claude["env"]

codex = (home / ".codex/config.toml").read_text()
assert 'model = "gpt-test"' in codex and 'added_later = "yes"' in codex
assert "[otel]" not in codex and "flowlines" not in codex and "[features]" not in codex

hooks = json.loads((home / ".codex/hooks.json").read_text())["hooks"]
assert [h["command"] for g in hooks["Stop"] for h in g["hooks"]] == ["echo existing"]
assert [h["command"] for g in hooks["UserPromptSubmit"] for h in g["hooks"]] == ["echo added later"]
assert "PostToolUse" not in hooks
PY

# --- state from the previous installer version is upgraded on repair ------------------------

cp "${FLOWLINES_TEST_ROOT}/claude.original" "${FLOWLINES_AGENT_HOME}/.claude/settings.json"
cp "${FLOWLINES_TEST_ROOT}/codex.original" "${FLOWLINES_AGENT_HOME}/.codex/config.toml"
cp "${FLOWLINES_TEST_ROOT}/hooks.original" "${FLOWLINES_AGENT_HOME}/.codex/hooks.json"
"${FLOWLINES_SCRIPT_DIR}/install.sh" --target both --non-interactive >/dev/null
python3 - <<'PY'
# The previous version recorded only paths, backups, and hashes.
import json
import os
from pathlib import Path

state_path = Path(os.environ["FLOWLINES_STATE"]) / "state.json"
state = json.loads(state_path.read_text())
for item in state["files"].values():
    for key in ("managed_original", "removed_env", "removed_toml", "events_original", "env_absent_originally"):
        item.pop(key, None)
state["version"] = 1
state_path.write_text(json.dumps(state, indent=2) + "\n")
PY
"${FLOWLINES_SCRIPT_DIR}/install.sh" --target both --non-interactive >/dev/null
python3 - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ["FLOWLINES_AGENT_HOME"])
claude_path = home / ".claude/settings.json"
claude = json.loads(claude_path.read_text())
claude["env"]["ADDED_LATER"] = "1"
claude_path.write_text(json.dumps(claude) + "\n")
codex_path = home / ".codex/config.toml"
codex_path.write_text(codex_path.read_text() + '\n[custom]\nadded_later = "yes"\n')
PY
"${FLOWLINES_SCRIPT_DIR}/uninstall.sh" >/dev/null
python3 - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ["FLOWLINES_AGENT_HOME"])
claude = json.loads((home / ".claude/settings.json").read_text())
assert claude["env"] == {"KEEP_ME": "yes", "ADDED_LATER": "1"}, claude["env"]
codex = (home / ".codex/config.toml").read_text()
assert "flowlines" not in codex and "[otel]" not in codex and "[features]" not in codex, codex
assert 'model = "gpt-test"' in codex and 'added_later = "yes"' in codex
hooks = json.loads((home / ".codex/hooks.json").read_text())["hooks"]
assert [h["command"] for g in hooks["Stop"] for h in g["hooks"]] == ["echo existing"]
assert "UserPromptSubmit" not in hooks and "PostToolUse" not in hooks
PY

# --- existing exporters are never silently replaced -----------------------------------------

python3 - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ["FLOWLINES_AGENT_HOME"])
(home / ".claude/settings.json").write_text(json.dumps({
    "env": {"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "https://collector.example/v1/logs"}
}) + "\n")
(home / ".codex/config.toml").write_text(
    'model = "gpt-test"\n\n[otel]\nenvironment = "dev"\n\n'
    '[otel.exporter.otlp-http]\nendpoint = "https://collector.example/v1/logs"\nprotocol = "binary"\n'
)
PY
cp "${FLOWLINES_AGENT_HOME}/.claude/settings.json" "${FLOWLINES_TEST_ROOT}/claude.conflict"
cp "${FLOWLINES_AGENT_HOME}/.codex/config.toml" "${FLOWLINES_TEST_ROOT}/codex.conflict"
if "${FLOWLINES_SCRIPT_DIR}/install.sh" --target claude --non-interactive >/dev/null 2>"${FLOWLINES_TEST_ROOT}/stderr"; then
  printf '%s\n' "install must refuse to divert existing Claude exporters" >&2
  exit 1
fi
grep -q OTEL_EXPORTER_OTLP_LOGS_ENDPOINT "${FLOWLINES_TEST_ROOT}/stderr"
if "${FLOWLINES_SCRIPT_DIR}/install.sh" --target codex --non-interactive >/dev/null 2>"${FLOWLINES_TEST_ROOT}/stderr"; then
  printf '%s\n' "install must refuse to replace an existing Codex exporter" >&2
  exit 1
fi
grep -q 'otel.exporter' "${FLOWLINES_TEST_ROOT}/stderr"
cmp "${FLOWLINES_AGENT_HOME}/.claude/settings.json" "${FLOWLINES_TEST_ROOT}/claude.conflict"
cmp "${FLOWLINES_AGENT_HOME}/.codex/config.toml" "${FLOWLINES_TEST_ROOT}/codex.conflict"
[ ! -e "${FLOWLINES_STATE}" ]

# Uninstall after a refusal must not touch the exporters it never replaced.
"${FLOWLINES_SCRIPT_DIR}/uninstall.sh" >/dev/null
cmp "${FLOWLINES_AGENT_HOME}/.claude/settings.json" "${FLOWLINES_TEST_ROOT}/claude.conflict"
cmp "${FLOWLINES_AGENT_HOME}/.codex/config.toml" "${FLOWLINES_TEST_ROOT}/codex.conflict"

# With --target both, a Codex refusal must leave Claude untouched as well.
printf '%s\n' '{"theme":"dark"}' > "${FLOWLINES_AGENT_HOME}/.claude/settings.json"
cp "${FLOWLINES_AGENT_HOME}/.claude/settings.json" "${FLOWLINES_TEST_ROOT}/claude.clean"
if "${FLOWLINES_SCRIPT_DIR}/install.sh" --target both --non-interactive >/dev/null 2>"${FLOWLINES_TEST_ROOT}/stderr"; then
  printf '%s\n' "install must refuse both targets when one conflicts" >&2
  exit 1
fi
cmp "${FLOWLINES_AGENT_HOME}/.claude/settings.json" "${FLOWLINES_TEST_ROOT}/claude.clean"
[ ! -e "${FLOWLINES_STATE}" ]
if "${FLOWLINES_SCRIPT_DIR}/doctor.sh" >/dev/null 2>&1; then
  printf '%s\n' "doctor must report a refused installation as not installed" >&2
  exit 1
fi
cp "${FLOWLINES_TEST_ROOT}/claude.conflict" "${FLOWLINES_AGENT_HOME}/.claude/settings.json"

"${FLOWLINES_SCRIPT_DIR}/install.sh" --target both --non-interactive --replace-existing-otel >/dev/null
"${FLOWLINES_SCRIPT_DIR}/doctor.sh" >/dev/null
python3 - <<'PY'
import json
import os
import re
from pathlib import Path

home = Path(os.environ["FLOWLINES_AGENT_HOME"])
env = json.loads((home / ".claude/settings.json").read_text())["env"]
assert "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT" not in env
assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "https://api.flowlines.ai"

codex = (home / ".codex/config.toml").read_text()
assert "[otel.exporter" not in codex, codex
assert 'environment = "production"' in codex
try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None
if tomllib is not None:
    parsed = tomllib.loads(codex)
    assert parsed["otel"]["exporter"]["otlp-http"]["endpoint"] == "https://api.flowlines.ai/v1/logs"
    assert parsed["features"]["hooks"] is True
PY
"${FLOWLINES_SCRIPT_DIR}/uninstall.sh" >/dev/null
python3 - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ["FLOWLINES_AGENT_HOME"])
env = json.loads((home / ".claude/settings.json").read_text())["env"]
assert env == {"OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "https://collector.example/v1/logs"}, env
codex = (home / ".codex/config.toml").read_text()
assert '[otel.exporter.otlp-http]' in codex and 'environment = "dev"' in codex and "flowlines" not in codex
PY

# --- API base validation ---------------------------------------------------------------------

printf '%s\n' '{"theme":"dark"}' > "${FLOWLINES_AGENT_HOME}/.claude/settings.json"
for FLOWLINES_BAD_BASE in "http://localhost.evil.example" "http://collector.example" "https://user:pw@api.flowlines.ai" "ftp://api.flowlines.ai"; do
  if "${FLOWLINES_SCRIPT_DIR}/install.sh" --target claude --non-interactive --api-base "${FLOWLINES_BAD_BASE}" >/dev/null 2>"${FLOWLINES_TEST_ROOT}/stderr"; then
    printf '%s\n' "install must reject ${FLOWLINES_BAD_BASE}" >&2
    exit 1
  fi
  grep -q -i 'https' "${FLOWLINES_TEST_ROOT}/stderr"
done
"${FLOWLINES_SCRIPT_DIR}/install.sh" --target claude --non-interactive --api-base "http://localhost:4318/" >/dev/null
grep -q '"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"' "${FLOWLINES_AGENT_HOME}/.claude/settings.json"
"${FLOWLINES_SCRIPT_DIR}/uninstall.sh" >/dev/null

# --- key files without a trailing newline are accepted --------------------------------------

printf '%s' 'sk-flowlines-file-secret' > "${FLOWLINES_TEST_ROOT}/key-file"
chmod 600 "${FLOWLINES_TEST_ROOT}/key-file"
(
  unset FLOWLINES_API_KEY
  FLOWLINES_API_KEY_FILE="${FLOWLINES_TEST_ROOT}/key-file" "${FLOWLINES_SCRIPT_DIR}/install.sh" --target claude --non-interactive >/dev/null
)
grep -q 'sk-flowlines-file-secret' "${FLOWLINES_AGENT_HOME}/.claude/settings.json"
"${FLOWLINES_SCRIPT_DIR}/uninstall.sh" >/dev/null
: > "${FLOWLINES_TEST_ROOT}/key-file"
if (unset FLOWLINES_API_KEY; FLOWLINES_API_KEY_FILE="${FLOWLINES_TEST_ROOT}/key-file" "${FLOWLINES_SCRIPT_DIR}/install.sh" --target claude --non-interactive >/dev/null 2>"${FLOWLINES_TEST_ROOT}/stderr"); then
  printf '%s\n' "install must reject an empty key file" >&2
  exit 1
fi
grep -q 'empty' "${FLOWLINES_TEST_ROOT}/stderr"

# --- files that did not exist are removed again, unless the user added to them --------------

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

"${FLOWLINES_SCRIPT_DIR}/install.sh" --target both --non-interactive >/dev/null
printf '%s\n' 'model = "added-later"' | cat - "${FLOWLINES_AGENT_HOME}/.codex/config.toml" > "${FLOWLINES_TEST_ROOT}/codex.tmp"
mv "${FLOWLINES_TEST_ROOT}/codex.tmp" "${FLOWLINES_AGENT_HOME}/.codex/config.toml"
"${FLOWLINES_SCRIPT_DIR}/uninstall.sh" >/dev/null
[ ! -e "${FLOWLINES_AGENT_HOME}/.claude/settings.json" ]
[ ! -e "${FLOWLINES_AGENT_HOME}/.codex/hooks.json" ]
grep -q 'model = "added-later"' "${FLOWLINES_AGENT_HOME}/.codex/config.toml"
! grep -q 'flowlines' "${FLOWLINES_AGENT_HOME}/.codex/config.toml"

printf '%s\n' "Installer tests passed."
