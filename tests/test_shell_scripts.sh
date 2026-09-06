#!/usr/bin/env bash
# ==============================================================================
# Linux Server Administration Suite: Shell Scripts Automated Integration Test
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_TMP_DIR="${SCRIPT_DIR}/tests/.tmp_test_run"

echo "=== [1/4] Validating Shell Syntax on all Scripts ==="
for f in "${SCRIPT_DIR}/bin/sys-admin-suite" \
         "${SCRIPT_DIR}/install.sh" \
         "${SCRIPT_DIR}/uninstall.sh" \
         "${SCRIPT_DIR}/reliability"/*.sh \
         "${SCRIPT_DIR}/provisioning/scripts"/*.sh; do
    echo "  Checking syntax: $(basename "$f")"
    bash -n "$f"
done
echo "All shell scripts passed syntax validation (bash -n)."

echo "=== [2/4] Testing backup_manager.sh End-to-End ==="
mkdir -p "$TEST_TMP_DIR"
export BACKUP_DIR="${TEST_TMP_DIR}/backups"
export BACKUP_TARGETS="${SCRIPT_DIR}/daemon/config.json"
export RETENTION_DAYS=1

# Run backup
bash "${SCRIPT_DIR}/reliability/backup_manager.sh" backup

# Verify backup
bash "${SCRIPT_DIR}/reliability/backup_manager.sh" verify

# List backups
bash "${SCRIPT_DIR}/reliability/backup_manager.sh" list

# Prune
bash "${SCRIPT_DIR}/reliability/backup_manager.sh" prune

echo "=== [3/4] Testing service_watchdog.sh Sweep ==="
# Monitored dummy services that are guaranteed to trigger simulated recovery in unprivileged mode
SERVICES_TO_MONITOR="dummy_daemon" bash "${SCRIPT_DIR}/reliability/service_watchdog.sh" || true

echo "=== [4/4] Testing bin/sys-admin-suite CLI ==="
"${SCRIPT_DIR}/bin/sys-admin-suite" version
"${SCRIPT_DIR}/bin/sys-admin-suite" help >/dev/null

# Clean up temporary test artifacts
rm -rf "$TEST_TMP_DIR"
rm -f "${SCRIPT_DIR}/syswatchdog_incidents.log"

echo ""
echo "======================================================="
echo "  ALL SHELL INTEGRATION TESTS PASSED SUCCESSFULLY!     "
echo "======================================================="
