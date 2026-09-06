#!/usr/bin/env bash
# ==============================================================================
# Linux Server Administration & Diagnostic Suite - Uninstaller
# ==============================================================================
set -euo pipefail

INSTALL_PREFIX="${INSTALL_PREFIX:-/usr/local}"

log_info() {
    echo -e "\033[0;32m[INFO]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

uninstall_system() {
    log_info "=== Removing Linux Server Diagnostic Suite (System-wide) ==="

    if command -v systemctl >/dev/null 2>&1; then
        systemctl disable --now syshealthd.service 2>/dev/null || true
    fi

    rm -f /etc/systemd/system/syshealthd.service
    rm -f /etc/logrotate.d/syshealthd
    rm -f /etc/cron.d/sys-maintenance
    rm -f "${INSTALL_PREFIX}/bin/sys-admin-suite" \
          "${INSTALL_PREFIX}/bin/syshealthd" \
          "${INSTALL_PREFIX}/bin/netdiag" \
          "${INSTALL_PREFIX}/bin/backup_manager.sh" \
          "${INSTALL_PREFIX}/bin/service_watchdog.sh"

    if command -v systemctl >/dev/null 2>&1; then
        systemctl daemon-reload
    fi

    log_info "Uninstallation complete. Configuration in /etc/syshealthd preserved."
}

uninstall_user() {
    local user_bin="${HOME}/.local/bin"
    rm -f "${user_bin}/sys-admin-suite" \
          "${user_bin}/syshealthd" \
          "${user_bin}/netdiag" \
          "${user_bin}/backup_manager.sh" \
          "${user_bin}/service_watchdog.sh"
    log_info "User-mode symlinks removed from ${user_bin}."
}

if [ "$(id -u)" -eq 0 ]; then
    uninstall_system
else
    uninstall_user
fi
