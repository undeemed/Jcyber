#!/usr/bin/env bash
# P0 gate: spec-doc consistency. Thin wrapper so `bash scripts/check_docs.sh`
# is the one command CI and the goal verification call.
set -euo pipefail
exec python3 "$(dirname "$0")/check_consistency.py" "$@"
