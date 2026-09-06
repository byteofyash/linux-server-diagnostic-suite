#!/usr/bin/env bash
# ==============================================================================
# Linux Server Administration Suite: SSH Hardening & Key Authentication
# Disables password authentication, disables root login, enforces key exchange.
# ==============================================================================
set -euo pipefail

SSHD_CONFIG_DIR="/etc/ssh/sshd_config.d"
HARDENING_FILE="${SSHD_CONFIG_DIR}/99-server-hardening.conf"
MAIN_SSHD_CONFIG="/etc/ssh/sshd_config"

log_info() {
    echo -e "\033[0;32m[INFO]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "\033[1;33m[WARN]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

harden_sshd() {
    log_info "=== Applying OpenSSH Security Hardening Configuration ==="

    local config_content="
# Linux Server Diagnostic Suite - Security Hardening
# Enforce Key-Based Authentication and Strict Access Controls

# Disable direct root login
PermitRootLogin no

# Enforce Public Key Authentication only
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys

# Explicitly disable password & PAM interactive authentication
PasswordAuthentication no
PermitEmptyPasswords no
KbdInteractiveAuthentication no

# Connection timeout and brute-force mitigation
MaxAuthTries 3
MaxSessions 5
LoginGraceTime 30s
ClientAliveInterval 300
ClientAliveCountMax 2

# Disable unnecessary features
X11Forwarding no
AllowTcpForwarding yes
Banner none
PrintMotd no
"

    if [ "$(id -u)" -ne 0 ]; then
        log_warn "Running without root privileges. Hardening configuration preview:"
        echo "$config_content"
        return 0
    fi

    # Check if sshd_config.d is supported
    if [ -d "$SSHD_CONFIG_DIR" ]; then
        log_info "Writing drop-in configuration to ${HARDENING_FILE}..."
        echo "$config_content" > "$HARDENING_FILE"
        chmod 600 "$HARDENING_FILE"
    else
        log_info "Appending security directives directly to ${MAIN_SSHD_CONFIG}..."
        cp "$MAIN_SSHD_CONFIG" "${MAIN_SSHD_CONFIG}.bak.$(date +%s)"
        echo "$config_content" >> "$MAIN_SSHD_CONFIG"
    fi

    log_info "Validating SSH daemon syntax using sshd -t..."
    if command -v sshd >/dev/null 2>&1; then
        if sshd -t; then
            log_info "SSHD configuration verified valid."
            if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet ssh; then
                systemctl reload ssh || systemctl restart ssh
                log_info "SSH service reloaded successfully."
            elif command -v service >/dev/null 2>&1; then
                service ssh reload || service ssh restart
            fi
        else
            log_error "sshd syntax validation failed! Reverting changes..."
            [ -f "$HARDENING_FILE" ] && rm -f "$HARDENING_FILE"
            exit 1
        fi
    else
        log_warn "sshd binary not found in PATH; skipping test."
    fi

    log_info "SSH hardening successfully completed."
}

harden_sshd "$@"
