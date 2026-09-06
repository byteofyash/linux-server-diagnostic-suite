#!/usr/bin/env bash
# ==============================================================================
# Linux Server Administration & Diagnostic Suite - Automated Installer
# Installs binaries, systemd service units, logrotate routines, and cron jobs.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_PREFIX="${INSTALL_PREFIX:-/usr/local}"
ENABLE_DAEMON="${1:-}"

log_info() {
    echo -e "\033[0;32m[INFO]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "\033[1;33m[WARN]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

make_executable() {
    log_info "Setting execution permissions on scripts..."
    chmod +x "${SCRIPT_DIR}/bin/sys-admin-suite" \
             "${SCRIPT_DIR}/daemon/syshealthd.py" \
             "${SCRIPT_DIR}/diagnostics/netdiag.py" \
             "${SCRIPT_DIR}/reliability/backup_manager.sh" \
             "${SCRIPT_DIR}/reliability/service_watchdog.sh" \
             "${SCRIPT_DIR}/provisioning/scripts"/*.sh 2>/dev/null || true
}

install_system() {
    log_info "=== Installing Linux Server Diagnostic Suite (System-wide) ==="

    # 1. Install CLI binaries
    mkdir -p "${INSTALL_PREFIX}/bin"
    ln -sf "${SCRIPT_DIR}/bin/sys-admin-suite" "${INSTALL_PREFIX}/bin/sys-admin-suite"
    ln -sf "${SCRIPT_DIR}/daemon/syshealthd.py" "${INSTALL_PREFIX}/bin/syshealthd"
    ln -sf "${SCRIPT_DIR}/diagnostics/netdiag.py" "${INSTALL_PREFIX}/bin/netdiag"
    ln -sf "${SCRIPT_DIR}/reliability/backup_manager.sh" "${INSTALL_PREFIX}/bin/backup_manager.sh"
    ln -sf "${SCRIPT_DIR}/reliability/service_watchdog.sh" "${INSTALL_PREFIX}/bin/service_watchdog.sh"
    log_info "Binaries linked to ${INSTALL_PREFIX}/bin."

    # 2. Configuration directory
    mkdir -p /etc/syshealthd
    if [ ! -f /etc/syshealthd/config.json ]; then
        cp "${SCRIPT_DIR}/daemon/config.json" /etc/syshealthd/config.json
        chmod 644 /etc/syshealthd/config.json
        log_info "Created configuration at /etc/syshealthd/config.json."
    fi

    # 3. Backup and log directories
    mkdir -p /var/backups/sys-diagnostics
    mkdir -p /var/log

    # 4. Install systemd service
    if [ -d /etc/systemd/system ]; then
        cp "${SCRIPT_DIR}/daemon/systemd/syshealthd.service" /etc/systemd/system/syshealthd.service
        chmod 644 /etc/systemd/system/syshealthd.service
        if command -v systemctl >/dev/null 2>&1; then
            systemctl daemon-reload
            log_info "Registered systemd unit: syshealthd.service"
            if [ "$ENABLE_DAEMON" = "--enable-daemon" ]; then
                systemctl enable --now syshealthd.service
                log_info "syshealthd.service enabled and started."
            else
                log_info "To start daemon: systemctl enable --now syshealthd.service"
            fi
        fi
    fi

    # 5. Install logrotate
    if [ -d /etc/logrotate.d ]; then
        cp "${SCRIPT_DIR}/reliability/logrotate/syshealthd.logrotate" /etc/logrotate.d/syshealthd
        chmod 644 /etc/logrotate.d/syshealthd
        log_info "Logrotate policy installed to /etc/logrotate.d/syshealthd."
    fi

    # 6. Install cron maintenance schedule
    if [ -d /etc/cron.d ]; then
        cp "${SCRIPT_DIR}/reliability/cron/sys-maintenance.cron" /etc/cron.d/sys-maintenance
        chmod 644 /etc/cron.d/sys-maintenance
        log_info "Cron maintenance schedule installed to /etc/cron.d/sys-maintenance."
    fi

    log_info "=== Installation Completed Successfully! ==="
    log_info "Run 'sys-admin-suite --help' to get started."
}

install_user() {
    log_warn "Installing in user/local mode (non-root)..."
    local user_bin="${HOME}/.local/bin"
    mkdir -p "$user_bin"

    ln -sf "${SCRIPT_DIR}/bin/sys-admin-suite" "${user_bin}/sys-admin-suite"
    ln -sf "${SCRIPT_DIR}/daemon/syshealthd.py" "${user_bin}/syshealthd"
    ln -sf "${SCRIPT_DIR}/diagnostics/netdiag.py" "${user_bin}/netdiag"
    ln -sf "${SCRIPT_DIR}/reliability/backup_manager.sh" "${user_bin}/backup_manager.sh"
    ln -sf "${SCRIPT_DIR}/reliability/service_watchdog.sh" "${user_bin}/service_watchdog.sh"

    log_info "User binaries linked to ${user_bin}."
    log_info "Ensure '${user_bin}' is in your PATH."
    log_info "To install systemd units, logrotate, and cron, run with sudo: sudo ./install.sh"
}

main() {
    make_executable
    if [ "$(id -u)" -eq 0 ]; then
        install_system
    else
        install_user
    fi
}

main "$@"
