"""
Disk Capacity and Inode Monitor Collector
Inspects block device filesystem capacity, free space, and inode exhaustion thresholds.
"""
import os
from typing import Dict, Any, List, Optional


class DiskCollector:
    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        self.thresholds = thresholds or {}
        self.mountpoints = self.thresholds.get("monitored_mountpoints", ["/"])

    def check_mountpoint(self, path: str) -> Optional[Dict[str, Any]]:
        """Samples filesystem stats using statvfs."""
        try:
            stat = os.statvfs(path)
            # Block calculations
            total_bytes = stat.f_blocks * stat.f_frsize
            free_bytes = stat.f_bfree * stat.f_frsize
            avail_bytes = stat.f_bavail * stat.f_frsize
            used_bytes = total_bytes - free_bytes

            capacity_pct = round((used_bytes / total_bytes * 100.0), 2) if total_bytes > 0 else 0.0

            # Inode calculations
            total_inodes = stat.f_files
            free_inodes = stat.f_ffree
            used_inodes = total_inodes - free_inodes
            inode_pct = round((used_inodes / total_inodes * 100.0), 2) if total_inodes > 0 else 0.0

            return {
                "mountpoint": path,
                "total_gb": round(total_bytes / (1024.0 ** 3), 2),
                "used_gb": round(used_bytes / (1024.0 ** 3), 2),
                "avail_gb": round(avail_bytes / (1024.0 ** 3), 2),
                "capacity_used_pct": capacity_pct,
                "total_inodes": total_inodes,
                "used_inodes": used_inodes,
                "free_inodes": free_inodes,
                "inodes_used_pct": inode_pct
            }
        except Exception as e:
            return {
                "mountpoint": path,
                "error": str(e),
                "capacity_used_pct": 0.0,
                "inodes_used_pct": 0.0
            }

    def collect(self) -> Dict[str, Any]:
        """Gathers storage metrics for all configured mount points."""
        warn_cap = self.thresholds.get("capacity_warning_pct", 80.0)
        crit_cap = self.thresholds.get("capacity_critical_pct", 90.0)
        warn_inode = self.thresholds.get("inode_warning_pct", 85.0)
        crit_inode = self.thresholds.get("inode_critical_pct", 95.0)

        partitions = []
        alerts = []
        overall_status = "OK"

        for mp in self.mountpoints:
            res = self.check_mountpoint(mp)
            if not res or "error" in res:
                continue

            partitions.append(res)
            cap_pct = res["capacity_used_pct"]
            inode_pct = res["inodes_used_pct"]

            if cap_pct >= crit_cap:
                overall_status = "CRITICAL"
                alerts.append(f"Disk partition '{mp}' critically full: {cap_pct}% used ({res['avail_gb']} GB remaining)")
            elif cap_pct >= warn_cap:
                if overall_status != "CRITICAL":
                    overall_status = "WARNING"
                alerts.append(f"Disk partition '{mp}' usage warning: {cap_pct}% used")

            if inode_pct >= crit_inode:
                overall_status = "CRITICAL"
                alerts.append(f"Inode exhaustion critical on '{mp}': {inode_pct}% inodes used")
            elif inode_pct >= warn_inode:
                if overall_status != "CRITICAL":
                    overall_status = "WARNING"
                alerts.append(f"Inode warning on '{mp}': {inode_pct}% inodes used")

        return {
            "partitions": partitions,
            "status": overall_status,
            "alerts": alerts
        }
