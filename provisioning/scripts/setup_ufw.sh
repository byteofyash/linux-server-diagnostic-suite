#!/usr/bin/env bash
# ==============================================================================
# Linux Server Administration Suite: UFW Firewall Provisioning
# Configures strict incoming firewall rules, rate-limited SSH, and diagnostic ports.
# ==============================================================================
set -euo pipefail

SSH_PORT="${SSH_PORT:-22}"
IPERF_PORT="${IPERF_PORT:-5201}"
METRICS_PORT="${METRICS_PORT:-9100}"
TRUSTED_SUBNET="${TRUSTED_SUBNET:-192.168.56.0/24}"

log_info() {
    echo -e "\033[0;32m[INFO]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "\033[1;33m[WARN]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

configure_ufw() {
    if ! command -v ufw >/dev/null 2>&1; then
        log_warn "UFW is not installed. Run 'apt-get install -y ufw' first."
        return 0
    fi

    if [ "$(id -u)" -ne 0 ]; then
        log_warn "Running without root privileges. Simulating UFW rules configuration:"
        echo "  - ufw default deny incoming"
        echo "  - ufw default allow outgoing"
        echo "  - ufw limit ${SSH_PORT}/tcp comment 'Rate-limited SSH'"
        echo "  - ufw allow from ${TRUSTED_SUBNET} to any port ${IPERF_PORT} proto tcp comment 'iperf3 TCP benchmark'"
        echo "  - ufw allow from ${TRUSTED_SUBNET} to any port ${IPERF_PORT} proto udp comment 'iperf3 UDP benchmark'"
        echo "  - ufw allow from ${TRUSTED_SUBNET} to any port ${METRICS_PORT} proto tcp comment 'Diagnostic metrics'"
        return 0
    fi

    log_info "Resetting existing UFW rules (preserving prompt)..."
    ufw --force reset

    log_info "Setting default policy: DROP incoming, ALLOW outgoing, DROP routed..."
    ufw default deny incoming
    ufw default allow outgoing
    ufw default deny forward

    log_info "Enabling rate limiting on SSH (port ${SSH_PORT}/tcp) to mitigate brute-force attempts..."
    ufw limit "${SSH_PORT}/tcp" comment "Rate-limited SSH access"

    log_info "Permitting iperf3 benchmarking (port ${IPERF_PORT} TCP/UDP) from trusted subnet ${TRUSTED_SUBNET}..."
    ufw allow from "${TRUSTED_SUBNET}" to any port "${IPERF_PORT}" proto tcp comment "iperf3 TCP diagnostic stream"
    ufw allow from "${TRUSTED_SUBNET}" to any port "${IPERF_PORT}" proto udp comment "iperf3 UDP jitter benchmark"

    log_info "Permitting local daemon metric inspection (port ${METRICS_PORT}/tcp)..."
    ufw allow from "${TRUSTED_SUBNET}" to any port "${METRICS_PORT}" proto tcp comment "System health telemetry"

    log_info "Enabling UFW logging level medium..."
    ufw logging medium

    log_info "Enabling UFW..."
    ufw --force enable

    log_info "=== Active UFW Firewall Status ==="
    ufw status verbose
}

configure_ufw "$@"
