#!/usr/bin/env bash
# ==============================================================================
# Linux Server Administration Suite: Service Watchdog & Auto-Recovery Engine
# Continuously verifies service health, detects hung/crashed states, triggers
# automated restart remediation, and writes incident post-mortem logs.
# ==============================================================================
set -euo pipefail

SERVICES_TO_MONITOR="${SERVICES_TO_MONITOR:-syshealthd ssh ufw}"
LOG_FILE="/var/log/syswatchdog_incidents.log"
FALLBACK_LOG="./syswatchdog_incidents.log"

log_info() {
    echo -e "\033[0;32m[INFO]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "\033[1;33m[WARN]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

get_incident_log() {
    if [ -w "$(dirname "$LOG_FILE" 2>/dev/null || echo ".")" ]; then
        echo "$LOG_FILE"
    else
        echo "$FALLBACK_LOG"
    fi
}

check_and_recover_service() {
    local service="$1"
    local has_systemctl=0
    local is_active=0

    if command -v systemctl >/dev/null 2>&1; then
        has_systemctl=1
        if systemctl is-active --quiet "$service"; then
            is_active=1
        fi
    else
        # Process check fallback
        if pgrep -f "$service" >/dev/null 2>&1; then
            is_active=1
        fi
    fi

    if [ "$is_active" -eq 1 ]; then
        log_info "Service '${service}' is healthy and running."
        return 0
    fi

    # Service Failure Detected!
    local inc_log
    inc_log="$(get_incident_log)"
    local timestamp
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    log_warn "CRITICAL: Service '${service}' is DOWN or UNRESPONSIVE!"
    echo "{\"timestamp\": \"${timestamp}\", \"service\": \"${service}\", \"event\": \"SERVICE_FAILURE_DETECTED\", \"action\": \"RESTART_INITIATED\"}" >> "$inc_log"

    log_info "Initiating automated recovery procedure for '${service}'..."
    if [ "$has_systemctl" -eq 1 ] && [ "$(id -u)" -eq 0 ]; then
        systemctl restart "$service" 2>&1 || true
        sleep 2
        if systemctl is-active --quiet "$service"; then
            log_info "Automated recovery SUCCESSFUL: Service '${service}' is back online."
            echo "{\"timestamp\": \"$(date -u '+%Y-%m-%dT%H:%M:%SZ')\", \"service\": \"${service}\", \"event\": \"RECOVERY_SUCCESSFUL\"}" >> "$inc_log"
            return 1
        else
            log_error "Automated recovery FAILED: Service '${service}' could not be restarted."
            echo "{\"timestamp\": \"$(date -u '+%Y-%m-%dT%H:%M:%SZ')\", \"service\": \"${service}\", \"event\": \"RECOVERY_FAILED\"}" >> "$inc_log"
            return 2
        fi
    else
        log_warn "[SIMULATION / UNPRIVILEGED] Auto-recovery command: systemctl restart ${service}"
        echo "{\"timestamp\": \"$(date -u '+%Y-%m-%dT%H:%M:%SZ')\", \"service\": \"${service}\", \"event\": \"SIMULATED_RESTART\"}" >> "$inc_log"
        return 1
    fi
}

main() {
    log_info "=== Executing Service Reliability Watchdog Sweep ==="
    local incidents=0

    for svc in $SERVICES_TO_MONITOR; do
        if ! check_and_recover_service "$svc"; then
            incidents=$((incidents + 1))
        fi
    done

    if [ "$incidents" -eq 0 ]; then
        log_info "All monitored services (${SERVICES_TO_MONITOR}) are healthy. Zero incidents."
        exit 0
    else
        log_warn "Watchdog completed with ${incidents} incident(s) detected and remediated."
        exit 1
    fi
}

main "$@"
