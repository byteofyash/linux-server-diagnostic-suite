#!/usr/bin/env python3
"""
System Health Monitoring Daemon (syshealthd)
Continuously monitors CPU load, memory leaks (RSS growth tracking),
and disk capacity. Managed via systemd service units.
"""
import os
import sys
import json
import time
import signal
import argparse
from typing import Dict, Any, Optional

# Ensure collectors package can be imported regardless of execution path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from collectors.cpu import CpuCollector
from collectors.memory import MemoryCollector
from collectors.disk import DiskCollector
from alerts import AlertDispatcher


class SysHealthDaemon:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join(current_dir, "config.json")
        self.config = self.load_config()
        self.running = False
        self.reload_requested = False

        # Initialize collectors
        thresholds = self.config.get("thresholds", {})
        self.cpu_collector = CpuCollector(thresholds.get("cpu", {}))
        self.memory_collector = MemoryCollector(thresholds.get("memory", {}))
        self.disk_collector = DiskCollector(thresholds.get("disk", {}))
        self.dispatcher = AlertDispatcher(self.config)

        # PID file determination
        daemon_cfg = self.config.get("daemon", {})
        primary_pid = daemon_cfg.get("pid_file", "/run/syshealthd.pid")
        fallback_pid = daemon_cfg.get("fallback_pid_file", "/tmp/syshealthd.pid")

        if os.path.exists(os.path.dirname(primary_pid)) and os.access(os.path.dirname(primary_pid), os.W_OK):
            self.pid_file = primary_pid
        else:
            self.pid_file = fallback_pid

    def load_config(self) -> Dict[str, Any]:
        """Loads configuration from JSON file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARN] Error reading {self.config_path}: {e}, using default configuration.", file=sys.stderr)
        return {}

    def handle_signals(self):
        """Attaches POSIX signal handlers."""
        def sig_term_handler(signum, frame):
            print(f"\n[INFO] Received termination signal ({signum}). Shutting down gracefully...")
            self.running = False

        def sig_hup_handler(signum, frame):
            print("\n[INFO] Received SIGHUP. Reloading configuration...")
            self.reload_requested = True

        signal.signal(signal.SIGINT, sig_term_handler)
        signal.signal(signal.SIGTERM, sig_term_handler)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, sig_hup_handler)

    def write_pid_file(self):
        """Records current PID."""
        try:
            with open(self.pid_file, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except Exception as e:
            print(f"[WARN] Could not write PID file {self.pid_file}: {e}", file=sys.stderr)

    def remove_pid_file(self):
        """Removes PID file upon exit."""
        if os.path.exists(self.pid_file):
            try:
                os.remove(self.pid_file)
            except Exception:
                pass

    def sample_system(self) -> Dict[str, Any]:
        """Executes one round of telemetry collection across all modular collectors."""
        cpu_data = self.cpu_collector.collect()
        mem_data = self.memory_collector.collect()
        disk_data = self.disk_collector.collect()

        statuses = [cpu_data.get("status"), mem_data.get("status"), disk_data.get("status")]
        if "CRITICAL" in statuses:
            overall_status = "CRITICAL"
        elif "WARNING" in statuses:
            overall_status = "WARNING"
        else:
            overall_status = "OK"

        all_alerts = cpu_data.get("alerts", []) + mem_data.get("alerts", []) + disk_data.get("alerts", [])

        return {
            "overall_status": overall_status,
            "alerts": all_alerts,
            "cpu": cpu_data,
            "memory": mem_data,
            "disk": disk_data
        }

    def run(self):
        """Main daemon loop."""
        self.handle_signals()
        self.write_pid_file()
        self.running = True

        poll_interval = self.config.get("daemon", {}).get("poll_interval_seconds", 5)
        print(f"[INFO] syshealthd started successfully (PID: {os.getpid()}, Poll interval: {poll_interval}s)")
        print(f"[INFO] Logging structured telemetry to: {self.dispatcher.log_path}")

        try:
            while self.running:
                if self.reload_requested:
                    self.config = self.load_config()
                    thresholds = self.config.get("thresholds", {})
                    self.cpu_collector.thresholds = thresholds.get("cpu", {})
                    self.memory_collector.thresholds = thresholds.get("memory", {})
                    self.disk_collector.thresholds = thresholds.get("disk", {})
                    poll_interval = self.config.get("daemon", {}).get("poll_interval_seconds", 5)
                    self.reload_requested = False
                    print(f"[INFO] Configuration reloaded successfully. Poll interval: {poll_interval}s")

                metrics = self.sample_system()
                self.dispatcher.dispatch(metrics)

                # Sleep in short increments to respond swiftly to signals
                sleep_start = time.time()
                while self.running and (time.time() - sleep_start < poll_interval):
                    time.sleep(0.5)

        finally:
            self.remove_pid_file()
            print("[INFO] syshealthd stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="syshealthd: Modular Linux System Health & Memory Leak Monitoring Daemon"
    )
    parser.add_argument("--config", "-c", type=str, default=None, help="Path to custom config.json")
    parser.add_argument("--foreground", "-f", action="store_true", help="Run daemon in foreground")
    parser.add_argument("--once", action="store_true", help="Run single sample check and output summary")
    parser.add_argument("--json", action="store_true", help="Run single sample and print JSON payload")

    args = parser.parse_args()
    daemon = SysHealthDaemon(config_path=args.config)

    if args.json:
        metrics = daemon.sample_system()
        print(json.dumps(metrics, indent=2))
        sys.exit(0)

    if args.once:
        metrics = daemon.sample_system()
        status = metrics["overall_status"]
        cpu = metrics["cpu"]
        mem = metrics["memory"]["stats"]
        leaks = metrics["memory"]["leak_suspects"]
        disk = metrics["disk"]["partitions"]

        print(f"System Health Status: {status}")
        print(f"CPU: {cpu.get('utilization_pct')}% (Cores: {cpu.get('cores')}, 1m Load: {cpu['load_average']['1m']})")
        print(f"RAM: {mem.get('ram_used_pct')}% ({mem.get('ram_used_mb')} MB / {mem.get('ram_total_mb')} MB)")
        print(f"Swap: {mem.get('swap_used_pct')}%")
        print(f"Disk Partitions Inspected: {len(disk)}")
        for d in disk:
            print(f"  - {d.get('mountpoint')}: {d.get('capacity_used_pct')}% used ({d.get('avail_gb')} GB avail), Inodes: {d.get('inodes_used_pct')}%")

        if leaks:
            print(f"\n[ALERT] {len(leaks)} Potential Memory Leak(s) Detected:")
            for lk in leaks:
                print(f"  - PID {lk['pid']} ({lk['process']}): +{lk['growth_delta_mb']} MB growth over {lk['samples_evaluated']} samples")
        else:
            print("Memory Leak Watchdog: No anomalous monotonic RSS expansion detected.")

        if metrics["alerts"]:
            print("\nActive Alerts:")
            for alt in metrics["alerts"]:
                print(f"  * {alt}")

        exit_code = 0 if status == "OK" else (1 if status == "WARNING" else 2)
        sys.exit(exit_code)

    # Standard execution
    daemon.run()


if __name__ == "__main__":
    main()
