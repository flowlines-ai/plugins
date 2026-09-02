#!/bin/sh

# Codex command hooks must never block or alter the agent because telemetry failed.
set +e
umask 077

FLOWLINES_AGENT_HOME="${FLOWLINES_AGENT_HOME:-${HOME}}"
FLOWLINES_AGENT_CONFIG_HOME="${FLOWLINES_AGENT_CONFIG_HOME:-${XDG_CONFIG_HOME:-${FLOWLINES_AGENT_HOME}/.config}}"
FLOWLINES_STATE_DIR="${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability"
FLOWLINES_SPOOL_DIR="${FLOWLINES_STATE_DIR}/spool"
FLOWLINES_CURL_CONFIG="${FLOWLINES_STATE_DIR}/curl.conf"
FLOWLINES_MAX_EVENT_BYTES=8388608
FLOWLINES_MAX_ATTEMPTS=20

mkdir -p "${FLOWLINES_SPOOL_DIR}" >/dev/null 2>&1
chmod 700 "${FLOWLINES_STATE_DIR}" "${FLOWLINES_SPOOL_DIR}" >/dev/null 2>&1

FLOWLINES_EVENT_FILE="${FLOWLINES_SPOOL_DIR}/$(date +%s)-$$.json"
head -c "$((FLOWLINES_MAX_EVENT_BYTES + 1))" > "${FLOWLINES_EVENT_FILE}" 2>/dev/null
FLOWLINES_EVENT_SIZE="$(wc -c < "${FLOWLINES_EVENT_FILE}" 2>/dev/null | tr -d ' ')"
case "${FLOWLINES_EVENT_SIZE}" in
  ''|*[!0-9]*) rm -f "${FLOWLINES_EVENT_FILE}" ;;
  *)
    if [ "${FLOWLINES_EVENT_SIZE}" -eq 0 ] || [ "${FLOWLINES_EVENT_SIZE}" -gt "${FLOWLINES_MAX_EVENT_BYTES}" ]; then
      rm -f "${FLOWLINES_EVENT_FILE}"
    fi
    ;;
esac

# Keep at most the newest 100 pending events. Timestamp-prefixed names sort oldest first.
set -- "${FLOWLINES_SPOOL_DIR}"/*.json
if [ -f "$1" ]; then
  while [ "$#" -gt 100 ]; do
    rm -f "$1"
    shift
  done
fi

if [ -r "${FLOWLINES_CURL_CONFIG}" ] && command -v curl >/dev/null 2>&1; then
  FLOWLINES_ATTEMPTS=0
  for FLOWLINES_PENDING in "${FLOWLINES_SPOOL_DIR}"/*.json; do
    [ -f "${FLOWLINES_PENDING}" ] || break
    FLOWLINES_ATTEMPTS=$((FLOWLINES_ATTEMPTS + 1))
    [ "${FLOWLINES_ATTEMPTS}" -le "${FLOWLINES_MAX_ATTEMPTS}" ] || break
    FLOWLINES_PENDING_NAME=${FLOWLINES_PENDING##*/}
    FLOWLINES_EVENT_TIME_UNIX=${FLOWLINES_PENDING_NAME%%-*}
    FLOWLINES_HTTP_STATUS=$(curl --config "${FLOWLINES_CURL_CONFIG}" \
      --connect-timeout 1 \
      --max-time 3 \
      --silent \
      --output /dev/null \
      --write-out '%{http_code}' \
      --header "x-flowlines-event-time-unix: ${FLOWLINES_EVENT_TIME_UNIX}" \
      --data-binary "@${FLOWLINES_PENDING}" 2>/dev/null)
    FLOWLINES_CURL_EXIT=$?
    case "${FLOWLINES_HTTP_STATUS}" in
      2??) [ "${FLOWLINES_CURL_EXIT}" -eq 0 ] && rm -f "${FLOWLINES_PENDING}" ;;
      4??) rm -f "${FLOWLINES_PENDING}" ;;
    esac
  done
fi

printf '{}\n'
exit 0
