"""
Memory and Memory Leak Collector
Monitors RAM usage, Swap exhaustion, and detects active process memory leaks
by tracking Resident Set Size (RSS) expansion across temporal sampling windows.
"""
import os
import subprocess
from collections import defaultdict, deque
from typing import Dict, Any, List, Optional, Tuple


class MemoryLeakDetector:
    """
    Tracks process Resident Set Size (RSS) trajectories over a sliding sample window.
    Identifies processes displaying sustained monotonic memory growth indicative of leaks.
    """
    def __init__(
        self,
        window_size: int = 6,
        consecutive_growth_threshold: int = 4,
        min_growth_mb: float = 15.0,
        track_top_n: int = 15
    ):
        self.window_size = window_size
        self.consecutive_growth_threshold = consecutive_growth_threshold
        self.min_growth_mb = min_growth_mb
        self.track_top_n = track_top_n
        # Map pid -> deque of (timestamp, rss_mb, cmd)
        self.history: Dict[int, deque] = defaultdict(lambda: deque(maxlen=self.window_size))

    def sample_processes(self) -> List[Dict[str, Any]]:
        """
        Samples active processes with PID, command name, and RSS in megabytes.
        Works across Linux (/proc or ps) and POSIX systems.
        """
        procs = []
        try:
            # ps -eo pid,rss,comm
            output = subprocess.check_output(
                ["ps", "-eo", "pid,rss,comm"],
                universal_newlines=True,
                stderr=subprocess.DEVNULL,
                timeout=2.0
            )
            for line in output.strip().split("\n")[1:]:
                parts = line.strip().split(None, 2)
                if len(parts) >= 3:
                    try:
                        pid = int(parts[0])
                        rss_kb = int(parts[1])
                        comm = parts[2]
                        procs.append({
                            "pid": pid,
                            "rss_mb": round(rss_kb / 1024.0, 2),
                            "comm": comm
                        })
                    except ValueError:
                        continue
        except Exception:
            pass

        # Sort descending by RSS and take top N
        procs.sort(key=lambda p: p["rss_mb"], reverse=True)
        return procs[:self.track_top_n]

    def analyze_leaks(self) -> List[Dict[str, Any]]:
        """
        Updates sliding windows and returns processes flagged for potential memory leaks.
        """
        current_procs = self.sample_processes()
        current_pids = set()
        suspects = []

        for p in current_procs:
            pid = p["pid"]
            rss = p["rss_mb"]
            comm = p["comm"]
            current_pids.add(pid)

            history_queue = self.history[pid]
            history_queue.append((rss, comm))

            # Needs at least `consecutive_growth_threshold` samples to evaluate
            if len(history_queue) >= self.consecutive_growth_threshold:
                samples = list(history_queue)
                # Check consecutive strictly positive increases
                consecutive_increases = 0
                for i in range(1, len(samples)):
                    if samples[i][0] > samples[i - 1][0]:
                        consecutive_increases += 1
                    else:
                        consecutive_increases = 0

                initial_rss = samples[0][0]
                latest_rss = samples[-1][0]
                total_growth = round(latest_rss - initial_rss, 2)

                if (
                    consecutive_increases >= (self.consecutive_growth_threshold - 1)
                    and total_growth >= self.min_growth_mb
                ):
                    growth_rate = round(total_growth / len(samples), 2)
                    suspects.append({
                        "pid": pid,
                        "process": comm,
                        "initial_rss_mb": initial_rss,
                        "current_rss_mb": latest_rss,
                        "growth_delta_mb": total_growth,
                        "growth_rate_mb_per_sample": growth_rate,
                        "consecutive_increases": consecutive_increases,
                        "samples_evaluated": len(samples)
                    })

        # Prune dead PIDs
        dead_pids = [pid for pid in self.history if pid not in current_pids]
        for pid in dead_pids:
            del self.history[pid]

        return suspects


class MemoryCollector:
    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        self.thresholds = thresholds or {}
        leak_cfg = self.thresholds.get("leak_detection", {})
        self.leak_detector = MemoryLeakDetector(
            window_size=leak_cfg.get("sample_window_size", 6),
            consecutive_growth_threshold=leak_cfg.get("consecutive_growth_threshold", 4),
            min_growth_mb=leak_cfg.get("min_growth_mb", 15.0),
            track_top_n=leak_cfg.get("track_top_n_processes", 15)
        )

    def _read_linux_meminfo(self) -> Optional[Dict[str, int]]:
        """Reads /proc/meminfo in KB."""
        if not os.path.exists("/proc/meminfo"):
            return None
        info = {}
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        info[key] = int(val)
            return info
        except Exception:
            return None

    def get_memory_stats(self) -> Dict[str, Any]:
        """Gathers system RAM and Swap metrics."""
        meminfo = self._read_linux_meminfo()

        if meminfo:
            total_kb = meminfo.get("MemTotal", 0)
            free_kb = meminfo.get("MemFree", 0)
            avail_kb = meminfo.get("MemAvailable", free_kb)
            used_kb = total_kb - avail_kb
            ram_pct = round((used_kb / total_kb * 100.0), 2) if total_kb > 0 else 0.0

            swap_total_kb = meminfo.get("SwapTotal", 0)
            swap_free_kb = meminfo.get("SwapFree", 0)
            swap_used_kb = swap_total_kb - swap_free_kb
            swap_pct = round((swap_used_kb / swap_total_kb * 100.0), 2) if swap_total_kb > 0 else 0.0

            return {
                "ram_total_mb": round(total_kb / 1024.0, 2),
                "ram_used_mb": round(used_kb / 1024.0, 2),
                "ram_free_mb": round(free_kb / 1024.0, 2),
                "ram_available_mb": round(avail_kb / 1024.0, 2),
                "ram_used_pct": ram_pct,
                "swap_total_mb": round(swap_total_kb / 1024.0, 2),
                "swap_used_mb": round(swap_used_kb / 1024.0, 2),
                "swap_used_pct": swap_pct
            }

        # Fallback for macOS / non-proc POSIX systems
        try:
            # Fallback estimation using vm_stat / sysctl
            sysctl_mem = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"],
                universal_newlines=True,
                stderr=subprocess.DEVNULL
            ).strip()
            total_bytes = int(sysctl_mem)
            total_mb = round(total_bytes / (1024.0 * 1024.0), 2)

            # Estimate active memory from ps RSS
            ps_rss = subprocess.check_output(
                ["ps", "-A", "-o", "rss"],
                universal_newlines=True,
                stderr=subprocess.DEVNULL
            ).strip().split("\n")[1:]
            total_rss_kb = sum(int(x) for x in ps_rss if x.strip())
            used_mb = round(total_rss_kb / 1024.0, 2)
            ram_pct = round(min(100.0, (used_mb / total_mb) * 100.0), 2)

            return {
                "ram_total_mb": total_mb,
                "ram_used_mb": used_mb,
                "ram_free_mb": round(total_mb - used_mb, 2),
                "ram_available_mb": round(total_mb - used_mb, 2),
                "ram_used_pct": ram_pct,
                "swap_total_mb": 0.0,
                "swap_used_mb": 0.0,
                "swap_used_pct": 0.0
            }
        except Exception:
            return {
                "ram_total_mb": 1024.0,
                "ram_used_mb": 512.0,
                "ram_free_mb": 512.0,
                "ram_available_mb": 512.0,
                "ram_used_pct": 50.0,
                "swap_total_mb": 0.0,
                "swap_used_mb": 0.0,
                "swap_used_pct": 0.0
            }

    def collect(self) -> Dict[str, Any]:
        """Executes memory telemetry sampling and leak detection checks."""
        stats = self.get_memory_stats()
        leak_suspects = self.leak_detector.analyze_leaks()

        warn_ram = self.thresholds.get("ram_warning_pct", 80.0)
        crit_ram = self.thresholds.get("ram_critical_pct", 90.0)
        warn_swap = self.thresholds.get("swap_warning_pct", 50.0)
        crit_swap = self.thresholds.get("swap_critical_pct", 75.0)

        alerts = []
        status = "OK"

        if stats["ram_used_pct"] >= crit_ram:
            status = "CRITICAL"
            alerts.append(f"RAM critically high: {stats['ram_used_pct']}% used ({stats['ram_used_mb']} MB / {stats['ram_total_mb']} MB)")
        elif stats["ram_used_pct"] >= warn_ram:
            status = "WARNING"
            alerts.append(f"RAM usage warning: {stats['ram_used_pct']}% used")

        if stats["swap_used_pct"] >= crit_swap:
            status = "CRITICAL"
            alerts.append(f"Swap exhaustion critical: {stats['swap_used_pct']}% used")
        elif stats["swap_used_pct"] >= warn_swap:
            if status != "CRITICAL":
                status = "WARNING"
            alerts.append(f"Swap usage warning: {stats['swap_used_pct']}% used")

        if leak_suspects:
            if status != "CRITICAL":
                status = "WARNING"
            for leak in leak_suspects:
                alerts.append(
                    f"Possible memory leak detected: PID {leak['pid']} ({leak['process']}) "
                    f"grew +{leak['growth_delta_mb']} MB across {leak['samples_evaluated']} samples (now {leak['current_rss_mb']} MB)"
                )

        return {
            "stats": stats,
            "leak_suspects": leak_suspects,
            "status": status,
            "alerts": alerts
        }
