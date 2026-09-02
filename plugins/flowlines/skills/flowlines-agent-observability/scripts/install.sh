#!/bin/sh

set -eu
umask 077

FLOWLINES_SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FLOWLINES_TARGET=auto
FLOWLINES_API_BASE_URL="${FLOWLINES_API_BASE_URL:-https://api.flowlines.ai}"
FLOWLINES_NON_INTERACTIVE=0
FLOWLINES_AGENT_HOME="${FLOWLINES_AGENT_HOME:-${HOME}}"

usage() {
  printf '%s\n' "Usage: install.sh [--target auto|claude|codex|both] [--api-base URL] [--non-interactive]"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      FLOWLINES_TARGET=$2
      shift 2
      ;;
    --api-base)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      FLOWLINES_API_BASE_URL=$2
      shift 2
      ;;
    --non-interactive)
      FLOWLINES_NON_INTERACTIVE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

case "$(uname -s)" in
  Darwin|Linux) ;;
  *) printf '%s\n' "Flowlines agent observability v1 supports macOS and Linux only." >&2; exit 1 ;;
esac

command -v python3 >/dev/null 2>&1 || {
  printf '%s\n' "python3 is required to merge JSON and TOML safely." >&2
  exit 1
}

if [ "${FLOWLINES_TARGET}" = "auto" ]; then
  FLOWLINES_HAS_CLAUDE=0
  FLOWLINES_HAS_CODEX=0
  if command -v claude >/dev/null 2>&1 || [ -d "${FLOWLINES_AGENT_HOME}/.claude" ]; then
    FLOWLINES_HAS_CLAUDE=1
  fi
  if command -v codex >/dev/null 2>&1 || [ -d "${FLOWLINES_AGENT_HOME}/.codex" ]; then
    FLOWLINES_HAS_CODEX=1
  fi
  if [ "${FLOWLINES_HAS_CLAUDE}" -eq 1 ] && [ "${FLOWLINES_HAS_CODEX}" -eq 1 ]; then
    FLOWLINES_TARGET=both
  elif [ "${FLOWLINES_HAS_CLAUDE}" -eq 1 ]; then
    FLOWLINES_TARGET=claude
  elif [ "${FLOWLINES_HAS_CODEX}" -eq 1 ]; then
    FLOWLINES_TARGET=codex
  else
    printf '%s\n' "Neither Claude Code nor Codex CLI was detected." >&2
    exit 1
  fi
fi

case "${FLOWLINES_TARGET}" in
  claude|codex|both) ;;
  *) usage >&2; exit 2 ;;
esac

if [ "${FLOWLINES_FULL_CONTENT_CONSENT:-}" != "yes" ]; then
  if [ "${FLOWLINES_NON_INTERACTIVE}" -eq 1 ] || [ ! -r /dev/tty ]; then
    printf '%s\n' "Set FLOWLINES_FULL_CONTENT_CONSENT=yes after explicit user consent." >&2
    exit 1
  fi
  printf '%s\n' "This exports full prompts, assistant responses, tool inputs, and tool outputs to Flowlines." >/dev/tty
  printf '%s' "Type EXPORT FULL CONTENT to consent: " >/dev/tty
  IFS= read -r FLOWLINES_CONSENT </dev/tty
  [ "${FLOWLINES_CONSENT}" = "EXPORT FULL CONTENT" ] || {
    printf '%s\n' "Consent not granted; no changes made." >&2
    exit 1
  }
  FLOWLINES_FULL_CONTENT_CONSENT=yes
  export FLOWLINES_FULL_CONTENT_CONSENT
fi

if [ -n "${FLOWLINES_API_KEY_FILE:-}" ]; then
  [ -r "${FLOWLINES_API_KEY_FILE}" ] || {
    printf '%s\n' "FLOWLINES_API_KEY_FILE is not readable." >&2
    exit 1
  }
  IFS= read -r FLOWLINES_API_KEY < "${FLOWLINES_API_KEY_FILE}"
elif [ -z "${FLOWLINES_API_KEY:-}" ]; then
  if [ "${FLOWLINES_NON_INTERACTIVE}" -eq 1 ] || [ ! -r /dev/tty ]; then
    printf '%s\n' "Provide FLOWLINES_API_KEY_FILE or FLOWLINES_API_KEY." >&2
    exit 1
  fi
  printf '%s' "Flowlines API key: " >/dev/tty
  FLOWLINES_STTY_STATE=$(stty -g </dev/tty 2>/dev/null || true)
  trap 'if [ -n "${FLOWLINES_STTY_STATE:-}" ]; then stty "${FLOWLINES_STTY_STATE}" </dev/tty 2>/dev/null || true; fi' 0 HUP INT TERM
  stty -echo </dev/tty 2>/dev/null || true
  IFS= read -r FLOWLINES_API_KEY </dev/tty
  if [ -n "${FLOWLINES_STTY_STATE}" ]; then
    stty "${FLOWLINES_STTY_STATE}" </dev/tty 2>/dev/null || true
  fi
  trap - 0 HUP INT TERM
  printf '\n' >/dev/tty
fi

[ -n "${FLOWLINES_API_KEY:-}" ] || {
  printf '%s\n' "The Flowlines API key cannot be empty." >&2
  exit 1
}

export FLOWLINES_API_KEY FLOWLINES_API_BASE_URL FLOWLINES_AGENT_HOME
python3 "${FLOWLINES_SCRIPT_DIR}/configure.py" install \
  --target "${FLOWLINES_TARGET}" \
  --relay-source "${FLOWLINES_SCRIPT_DIR}/codex-hook-relay.sh"
unset FLOWLINES_API_KEY

printf '%s\n' "Flowlines observability installed for ${FLOWLINES_TARGET}."
if [ "${FLOWLINES_TARGET}" = "codex" ] || [ "${FLOWLINES_TARGET}" = "both" ]; then
  printf '%s\n' "Open /hooks in Codex and trust the Flowlines user hooks before relying on codex exec telemetry."
fi
