#!/usr/bin/env bash
# ==============================================================================
# Linux Server Administration Suite: Automated Backup Manager
# Performs compressed archiving, SHA-256 cryptographic verification,
# automated retention pruning, and cron scheduling.
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/sys-diagnostics}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
BACKUP_ARCHIVE="${BACKUP_DIR}/sysbackup_${TIMESTAMP}.tar.gz"

# Default directories to back up (configurable via BACKUP_TARGETS)
DEFAULT_TARGETS="/etc/syshealthd /var/log/syshealthd.log"
BACKUP_TARGETS="${BACKUP_TARGETS:-$DEFAULT_TARGETS}"

log_info() {
    echo -e "\033[0;32m[INFO]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "\033[1;33m[WARN]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

compute_sha256() {
    local target_file="$1"
    local dir
    dir="$(dirname "$target_file")"
    local base
    base="$(basename "$target_file")"
    (
        cd "$dir"
        if command -v sha256sum >/dev/null 2>&1; then
            sha256sum "$base"
        elif command -v shasum >/dev/null 2>&1; then
            shasum -a 256 "$base"
        else
            log_error "No SHA-256 utility found."
            exit 1
        fi
    )
}

verify_sha256() {
    local checksum_file="$1"
    local dir
    dir="$(dirname "$checksum_file")"
    (
        cd "$dir"
        if command -v sha256sum >/dev/null 2>&1; then
            sha256sum -c "$(basename "$checksum_file")"
        elif command -v shasum >/dev/null 2>&1; then
            shasum -a 256 -c "$(basename "$checksum_file")"
        else
            log_error "No SHA-256 utility found."
            exit 1
        fi
    )
}

init_backup_dir() {
    if [ ! -d "$BACKUP_DIR" ]; then
        log_info "Creating backup repository at ${BACKUP_DIR}..."
        mkdir -p "$BACKUP_DIR"
    fi
}

run_backup() {
    init_backup_dir
    log_info "=== Starting Automated System Backup ==="
    log_info "Destination: ${BACKUP_ARCHIVE}"

    # Filter targets that actually exist
    local valid_targets=()
    for target in $BACKUP_TARGETS; do
        if [ -e "$target" ]; then
            valid_targets+=("$target")
        fi
    done

    if [ ${#valid_targets[@]} -eq 0 ]; then
        log_warn "None of the specified target directories/files exist: ${BACKUP_TARGETS}"
        log_info "Creating fallback snapshot of current diagnostic suite configuration..."
        local fallback_meta="${BACKUP_DIR}/metadata_${TIMESTAMP}.txt"
        echo "Backup created at ${TIMESTAMP} on $(hostname)" > "$fallback_meta"
        echo "Kernel: $(uname -a)" >> "$fallback_meta"
        valid_targets+=("$fallback_meta")
    fi

    log_info "Archiving and compressing ${#valid_targets[@]} target(s)..."
    tar -czf "$BACKUP_ARCHIVE" "${valid_targets[@]}" 2>/dev/null || tar -czf "$BACKUP_ARCHIVE" -C "$BACKUP_DIR" .

    # 1. Integrity test on the created tarball
    log_info "Validating gzip/tar archive integrity..."
    if tar -tzf "$BACKUP_ARCHIVE" >/dev/null 2>&1; then
        log_info "Tar archive integrity check: PASSED"
    else
        log_error "Corrupted archive generated! Aborting."
        rm -f "$BACKUP_ARCHIVE"
        exit 1
    fi

    # 2. Cryptographic SHA-256 Checksum Generation
    log_info "Computing SHA-256 cryptographic checksum..."
    local checksum_file="${BACKUP_ARCHIVE}.sha256"
    compute_sha256 "$BACKUP_ARCHIVE" > "$checksum_file"
    local checksum
    checksum="$(awk '{print $1}' "$checksum_file")"
    log_info "SHA-256: ${checksum}"

    # 3. Cryptographic Verification
    log_info "Verifying generated checksum signature..."
    if verify_sha256 "$checksum_file" >/dev/null 2>&1; then
        log_info "Cryptographic verification: PASSED"
    else
        log_error "Cryptographic checksum mismatch! Aborting."
        exit 1
    fi

    local archive_size
    archive_size="$(du -h "$BACKUP_ARCHIVE" | awk '{print $1}')"
    log_info "Backup successfully committed! Size: ${archive_size}"

    # Prune old archives
    prune_backups
}

verify_all() {
    init_backup_dir
    log_info "=== Verifying Integrity of All Stored Backups ==="
    local count=0
    local failed=0

    shopt -s nullglob
    local checksum_files=("${BACKUP_DIR}"/*.sha256)
    shopt -u nullglob

    if [ ${#checksum_files[@]} -eq 0 ]; then
        log_warn "No .sha256 checksum signatures found in ${BACKUP_DIR}."
        return 0
    fi

    for cfile in "${checksum_files[@]}"; do
        count=$((count + 1))
        local archive_file="${cfile%.sha256}"
        if [ ! -f "$archive_file" ]; then
            log_error "Missing archive file for signature: ${cfile}"
            failed=$((failed + 1))
            continue
        fi

        if verify_sha256 "$cfile" >/dev/null 2>&1 && tar -tzf "$archive_file" >/dev/null 2>&1; then
            log_info "[VALID] $(basename "$archive_file")"
        else
            log_error "[CORRUPT] $(basename "$archive_file")"
            failed=$((failed + 1))
        fi
    done

    log_info "Verification complete: ${count} verified, ${failed} failed."
    return "$failed"
}

list_backups() {
    init_backup_dir
    echo -e "\n=== Backup Catalog (${BACKUP_DIR}) ==="
    if [ -d "$BACKUP_DIR" ]; then
        ls -lh "$BACKUP_DIR"/*.tar.gz 2>/dev/null || echo "No backup archives stored."
    fi
    echo ""
}

prune_backups() {
    init_backup_dir
    log_info "Enforcing retention policy (Pruning archives older than ${RETENTION_DAYS} days)..."
    local pruned=0
    # Find files older than RETENTION_DAYS
    if [ -d "$BACKUP_DIR" ]; then
        while IFS= read -r -d '' file; do
            log_info "Pruning expired archive: $(basename "$file")"
            rm -f "$file" "${file}.sha256"
            pruned=$((pruned + 1))
        done < <(find "$BACKUP_DIR" -name "sysbackup_*.tar.gz" -mtime +"${RETENTION_DAYS}" -print0 2>/dev/null || true)
    fi
    log_info "Retention pruning complete: ${pruned} archive(s) pruned."
}

install_cron() {
    log_info "Installing automated cron schedule for backup tasks..."
    local cron_entry="0 2 * * * root ${PWD}/reliability/backup_manager.sh backup >> /var/log/sysbackup.log 2>&1"

    if [ "$(id -u)" -eq 0 ] && [ -d "/etc/cron.d" ]; then
        echo "$cron_entry" > /etc/cron.d/sysbackup-suite
        chmod 644 /etc/cron.d/sysbackup-suite
        log_info "Cron task registered at /etc/cron.d/sysbackup-suite"
    else
        log_info "[SIMULATION / USER CRON] Would add to crontab:"
        echo "  $cron_entry"
    fi
}

show_help() {
    echo "Usage: $0 {backup|verify|list|prune|install-cron}"
    echo ""
    echo "Commands:"
    echo "  backup        Create compressed timestamped backup with SHA-256 verification"
    echo "  verify        Verify checksums and tar integrity of all stored backups"
    echo "  list          List all available backups and their file sizes"
    echo "  prune         Prune backups older than RETENTION_DAYS (default: 7)"
    echo "  install-cron  Register automated daily backup in cron"
}

main() {
    local cmd="${1:-backup}"
    case "$cmd" in
        backup)
            run_backup
            ;;
        verify)
            verify_all
            ;;
        list)
            list_backups
            ;;
        prune)
            prune_backups
            ;;
        install-cron)
            install_cron
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unknown command: $cmd"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
