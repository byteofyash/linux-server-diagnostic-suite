"""
CPU Monitor Collector
Measures per-core and total CPU utilization, load averages (1m, 5m, 15m),
and normalized per-core load average.
"""
import os
import time
import subprocess
from typing import Dict, Any, Tuple, Optional


class CpuCollector:
    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        self.thresholds = thresholds or {}
        self.num_cores = os.cpu_count() or 1
        self._prev_stat_time: Optional[float] = None
        self._prev_total_ticks: Optional[int] = None
        self._prev_idle_ticks: Optional[int] = None

    def _read_proc_stat(self) -> Optional[Tuple[int, int]]:
        """Reads /proc/stat on Linux systems."""
        proc_stat_path = "/proc/stat"
        if not os.path.exists(proc_stat_path):
            return None
        try:
            with open(proc_stat_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("cpu "):
                        parts = [int(p) for p in line.split()[1:]]
                        # fields: user, nice, system, idle, iowait, irq, softirq, steal
                        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
                        total = sum(parts)
                        return total, idle
        except (IOError, ValueError):
            return None
        return None

    def get_load_averages(self) -> Tuple[float, float, float]:
        """Returns (1m, 5m, 15m) system load averages."""
        try:
            return os.getloadavg()
        except (AttributeError, OSError):
            proc_loadavg = "/proc/loadavg"
            if os.path.exists(proc_loadavg):
                try:
                    with open(proc_loadavg, "r", encoding="utf-8") as f:
                        parts = f.read().split()
                        return float(parts[0]), float(parts[1]), float(parts[2])
                except Exception:
                    pass
            return 0.0, 0.0, 0.0

    def get_cpu_utilization_pct(self) -> float:
        """
        Calculates instantaneous CPU utilization across sampling intervals.
        Falls back to sampling /proc/stat or top/ps.
        """
        proc_stat = self._read_proc_stat()
        now = time.time()

        if proc_stat:
            total, idle = proc_stat
            if self._prev_total_ticks is not None and self._prev_idle_ticks is not None:
                delta_total = total - self._prev_total_ticks
                delta_idle = idle - self._prev_idle_ticks
                self._prev_total_ticks = total
                self._prev_idle_ticks = idle
                self._prev_stat_time = now
                if delta_total > 0:
                    util = 100.0 * (1.0 - (delta_idle / delta_total))
                    return max(0.0, min(100.0, round(util, 2)))

            self._prev_total_ticks = total
            self._prev_idle_ticks = idle
            self._prev_stat_time = now

            # If first read, sleep brief 100ms or estimate from loadavg
            time.sleep(0.1)
            next_stat = self._read_proc_stat()
            if next_stat:
                n_total, n_idle = next_stat
                d_total = n_total - total
                d_idle = n_idle - idle
                self._prev_total_ticks = n_total
                self._prev_idle_ticks = n_idle
                if d_total > 0:
                    return max(0.0, min(100.0, round(100.0 * (1.0 - (d_idle / d_total)), 2)))

        # Fallback for macOS/BSD or non-/proc environments
        try:
            # Quick 1-sample check using ps summing active CPU
            output = subprocess.check_output(
                ["ps", "-A", "-o", "%cpu"],
                universal_newlines=True,
                stderr=subprocess.DEVNULL,
                timeout=1.0
            )
            total_cpu = sum(float(x) for x in output.strip().split("\n")[1:] if x.strip())
            norm_cpu = round(total_cpu / self.num_cores, 2)
            return max(0.0, min(100.0, norm_cpu))
        except Exception:
            # Fallback estimation using 1-min load average normalized to cores
            load_1m = self.get_load_averages()[0]
            estimated = round((load_1m / self.num_cores) * 100.0, 2)
            return max(0.0, min(100.0, estimated))

    def collect(self) -> Dict[str, Any]:
        """Gathers CPU telemetry and evaluates alert thresholds."""
        load_1m, load_5m, load_15m = self.get_load_averages()
        norm_load_1m = round(load_1m / self.num_cores, 3)
        norm_load_5m = round(load_5m / self.num_cores, 3)
        utilization_pct = self.get_cpu_utilization_pct()

        warn_load = self.thresholds.get("load_avg_warning_per_core", 1.5)
        crit_load = self.thresholds.get("load_avg_critical_per_core", 3.0)
        warn_util = self.thresholds.get("utilization_warning_pct", 80.0)
        crit_util = self.thresholds.get("utilization_critical_pct", 92.0)

        alerts = []
        status = "OK"

        if norm_load_1m >= crit_load or utilization_pct >= crit_util:
            status = "CRITICAL"
            alerts.append(
                f"High CPU load/utilization: {utilization_pct}% (1m load: {load_1m:.2f} across {self.num_cores} cores)"
            )
        elif norm_load_1m >= warn_load or utilization_pct >= warn_util:
            status = "WARNING"
            alerts.append(
                f"Elevated CPU load/utilization: {utilization_pct}% (1m load: {load_1m:.2f})"
            )

        return {
            "cores": self.num_cores,
            "load_average": {
                "1m": round(load_1m, 2),
                "5m": round(load_5m, 2),
                "15m": round(load_15m, 2),
                "normalized_1m": norm_load_1m
            },
            "utilization_pct": utilization_pct,
            "status": status,
            "alerts": alerts
        }
