#!/bin/sh

set -eu
FLOWLINES_SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "${FLOWLINES_SCRIPT_DIR}/configure.py" uninstall
