#!/usr/bin/env bash
# workload.sh - Wrapper chay tests/load/workload.py theo profile NFR-03 (10 / 30 / 60 RPS)
# TV4 so huu. Khong truyen secret qua argv.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_RPS="${1:-30}"
WARMUP_S="${WARMUP_DURATION:-120}"
STEADY_S="${STEADY_DURATION:-300}"

exec python3 "${SCRIPT_DIR}/workload.py" \
  --rps "${TARGET_RPS}" \
  --warmup "${WARMUP_S}" \
  --steady "${STEADY_S}" \
  --cred-file "${SCRIPT_DIR}/credentials.env"
