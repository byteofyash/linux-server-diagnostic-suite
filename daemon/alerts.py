"""
Alerting and Event Dispatcher
Handles logging, syslog integration, and structured JSON incident records.
"""
import os
import sys
import json
import time
import logging
from typing import Dict, Any, List, Optional


class AlertDispatcher:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        daemon_cfg = config.get("daemon", {})
        notif_cfg = config.get("notifications", {})

        # Determine writable log file
        primary_log = daemon_cfg.get("log_file", "/var/log/syshealthd.log")
        fallback_log = daemon_cfg.get("fallback_log_file", "syshealthd.log")

        if os.path.exists(os.path.dirname(primary_log)) and os.access(os.path.dirname(primary_log), os.W_OK):
            self.log_path = primary_log
        else:
            self.log_path = os.path.abspath(fallback_log)

        self.stdout_enabled = notif_cfg.get("stdout_enabled", True)
        self.json_log_enabled = notif_cfg.get("json_log_enabled", True)
        self.syslog_enabled = notif_cfg.get("syslog_enabled", True)

        self._setup_logger()

    def _setup_logger(self):
        self.logger = logging.getLogger("syshealthd")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []

        # File Handler (JSONL)
        try:
            file_handler = logging.FileHandler(self.log_path, encoding="utf-8")
            file_formatter = logging.Formatter("%(message)s")
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
        except Exception as e:
            print(f"[WARN] Failed to open log file {self.log_path}: {e}", file=sys.stderr)

    def dispatch(self, metrics: Dict[str, Any]):
        """Dispatches sampled metrics and evaluated alerts."""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        overall_status = metrics.get("overall_status", "OK")
        all_alerts = metrics.get("alerts", [])

        record = {
            "timestamp": timestamp,
            "overall_status": overall_status,
            "alerts": all_alerts,
            "cpu": metrics.get("cpu", {}),
            "memory": {
                "stats": metrics.get("memory", {}).get("stats", {}),
                "leaks": metrics.get("memory", {}).get("leak_suspects", [])
            },
            "disk": metrics.get("disk", {}).get("partitions", [])
        }

        # Write to structured JSON log
        if self.json_log_enabled and self.logger.handlers:
            self.logger.info(json.dumps(record))

        # Stdout logging with colors
        if self.stdout_enabled:
            color = "\033[0;32m" # Green for OK
            if overall_status == "WARNING":
                color = "\033[1;33m" # Yellow
            elif overall_status == "CRITICAL":
                color = "\033[0;31m" # Red

            reset = "\033[0m"
            cpu_util = metrics.get("cpu", {}).get("utilization_pct", 0)
            ram_util = metrics.get("memory", {}).get("stats", {}).get("ram_used_pct", 0)

            print(
                f"{color}[{overall_status}]{reset} {timestamp} | CPU: {cpu_util}% | RAM: {ram_util}%"
            )

            for alert in all_alerts:
                print(f"  {color}➔ {alert}{reset}")
