#!/bin/sh

# Codex command hooks must never block or alter the agent because telemetry failed.
# Codex runs these hooks synchronously with a 5 second timeout, so one relay run sends the
# current event plus a bounded slice of the backlog and always finishes well inside that.
set +e
umask 077

FLOWLINES_AGENT_HOME="${FLOWLINES_AGENT_HOME:-${HOME}}"
FLOWLINES_AGENT_CONFIG_HOME="${FLOWLINES_AGENT_CONFIG_HOME:-${XDG_CONFIG_HOME:-${FLOWLINES_AGENT_HOME}/.config}}"
FLOWLINES_STATE_DIR="${FLOWLINES_AGENT_CONFIG_HOME}/flowlines-agent-observability"
FLOWLINES_SPOOL_DIR="${FLOWLINES_STATE_DIR}/spool"
FLOWLINES_CURL_CONFIG="${FLOWLINES_STATE_DIR}/curl.conf"
FLOWLINES_MAX_EVENT_BYTES=8388608
FLOWLINES_MAX_BACKLOG_SENDS=5
FLOWLINES_SEND_BUDGET_SECONDS=2
FLOWLINES_STARTED_AT=$(date +%s)

mkdir -p "${FLOWLINES_SPOOL_DIR}" >/dev/null 2>&1
chmod 700 "${FLOWLINES_STATE_DIR}" "${FLOWLINES_SPOOL_DIR}" >/dev/null 2>&1

# Capture into a dotfile first so concurrent relays never see a half-written *.json event,
# then publish it with an atomic rename.
FLOWLINES_EVENT_FILE="${FLOWLINES_SPOOL_DIR}/${FLOWLINES_STARTED_AT}-$$.json"
FLOWLINES_INCOMING_FILE="${FLOWLINES_SPOOL_DIR}/.incoming-${FLOWLINES_STARTED_AT}-$$"
head -c "$((FLOWLINES_MAX_EVENT_BYTES + 1))" > "${FLOWLINES_INCOMING_FILE}" 2>/dev/null
FLOWLINES_EVENT_SIZE="$(wc -c < "${FLOWLINES_INCOMING_FILE}" 2>/dev/null | tr -d ' ')"
case "${FLOWLINES_EVENT_SIZE}" in
  ''|*[!0-9]*) rm -f "${FLOWLINES_INCOMING_FILE}" ;;
  *)
    if [ "${FLOWLINES_EVENT_SIZE}" -eq 0 ] || [ "${FLOWLINES_EVENT_SIZE}" -gt "${FLOWLINES_MAX_EVENT_BYTES}" ]; then
      rm -f "${FLOWLINES_INCOMING_FILE}"
    else
      mv -f "${FLOWLINES_INCOMING_FILE}" "${FLOWLINES_EVENT_FILE}" 2>/dev/null || rm -f "${FLOWLINES_INCOMING_FILE}"
    fi
    ;;
esac

# Keep at most the newest 100 pending events. Timestamp-prefixed names sort oldest first and
# the glob skips dotfiles, so events still being captured are never pruned or sent.
set -- "${FLOWLINES_SPOOL_DIR}"/*.json
if [ -f "$1" ]; then
  while [ "$#" -gt 100 ]; do
    rm -f "$1"
    shift
  done
fi

# Send one spooled event. Success and permanent client errors remove it; rate limiting (429),
# request timeouts (408), server errors, and network failures keep it for a later run.
flowlines_send() {
  flowlines_pending_name=${1##*/}
  flowlines_event_time_unix=${flowlines_pending_name%%-*}
  flowlines_http_status=$(curl --config "${FLOWLINES_CURL_CONFIG}" \
    --connect-timeout 1 \
    --max-time 2 \
    --silent \
    --output /dev/null \
    --write-out '%{http_code}' \
    --header "x-flowlines-event-time-unix: ${flowlines_event_time_unix}" \
    --data-binary "@$1" 2>/dev/null)
  flowlines_curl_exit=$?
  case "${flowlines_http_status}" in
    2??) [ "${flowlines_curl_exit}" -eq 0 ] && rm -f "$1" ;;
    408|429) ;;
    4??) rm -f "$1" ;;
  esac
}

flowlines_within_budget() {
  [ "$(( $(date +%s) - FLOWLINES_STARTED_AT ))" -lt "${FLOWLINES_SEND_BUDGET_SECONDS}" ]
}

if [ -r "${FLOWLINES_CURL_CONFIG}" ] && command -v curl >/dev/null 2>&1; then
  # The current event goes first so a backlog never starves fresh telemetry.
  [ -f "${FLOWLINES_EVENT_FILE}" ] && flowlines_send "${FLOWLINES_EVENT_FILE}"
  FLOWLINES_BACKLOG_SENDS=0
  for FLOWLINES_PENDING in "${FLOWLINES_SPOOL_DIR}"/*.json; do
    [ -f "${FLOWLINES_PENDING}" ] || break
    [ "${FLOWLINES_PENDING}" = "${FLOWLINES_EVENT_FILE}" ] && continue
    flowlines_within_budget || break
    FLOWLINES_BACKLOG_SENDS=$((FLOWLINES_BACKLOG_SENDS + 1))
    [ "${FLOWLINES_BACKLOG_SENDS}" -le "${FLOWLINES_MAX_BACKLOG_SENDS}" ] || break
    flowlines_send "${FLOWLINES_PENDING}"
  done
fi

printf '{}\n'
exit 0
