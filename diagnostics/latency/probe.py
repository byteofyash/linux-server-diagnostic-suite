"""
Network Latency & ICMP Probe
Measures round-trip time (RTT), jitter (mdev), and packet loss statistics.
"""
import re
import sys
import time
import socket
import platform
import subprocess
from typing import Dict, Any, Optional


class LatencyProbe:
    def __init__(self, target: str = "127.0.0.1", count: int = 5, timeout_sec: int = 2, tcp_port: Optional[int] = None):
        self.target = target
        self.count = count
        self.timeout_sec = timeout_sec
        self.tcp_port = tcp_port
        self.os_type = platform.system().lower()

    def run_tcp_syn_probe(self, port: int) -> Dict[str, Any]:
        """Measures TCP handshake latency directly when ICMP is filtered or sandboxed."""
        latencies = []
        transmitted = self.count
        received = 0

        for _ in range(self.count):
            start = time.perf_counter()
            try:
                s = socket.create_connection((self.target, port), timeout=self.timeout_sec)
                elapsed_ms = round((time.perf_counter() - start) * 1000.0, 3)
                s.close()
                latencies.append(elapsed_ms)
                received += 1
            except (socket.timeout, ConnectionRefusedError, OSError):
                pass
            time.sleep(0.05)

        loss_pct = round(((transmitted - received) / transmitted) * 100.0, 2)
        min_ms = min(latencies) if latencies else None
        avg_ms = round(sum(latencies) / len(latencies), 3) if latencies else None
        max_ms = max(latencies) if latencies else None
        # Standard deviation / jitter
        if len(latencies) > 1:
            mean = sum(latencies) / len(latencies)
            variance = sum((x - mean) ** 2 for x in latencies) / (len(latencies) - 1)
            mdev_ms = round(variance ** 0.5, 3)
        else:
            mdev_ms = 0.0 if latencies else None

        status = "OK" if loss_pct == 0.0 else ("DEGRADED" if received > 0 else "UNREACHABLE")
        return {
            "target": self.target,
            "status": status,
            "probe_type": f"TCP-SYN (port {port})",
            "packets_transmitted": transmitted,
            "packets_received": received,
            "packet_loss_pct": loss_pct,
            "rtt_min_ms": min_ms,
            "rtt_avg_ms": avg_ms,
            "rtt_max_ms": max_ms,
            "rtt_mdev_ms": mdev_ms
        }

    def run(self) -> Dict[str, Any]:
        """
        Executes ping diagnostic and parses RTT and packet loss.
        """
        cmd = ["ping", "-c", str(self.count)]
        if self.os_type == "linux":
            cmd.extend(["-W", str(self.timeout_sec)])
        elif self.os_type == "darwin":
            cmd.extend(["-W", str(self.timeout_sec * 1000)]) # macOS ping takes ms
        cmd.append(self.target)

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=(self.count * self.timeout_sec) + 3
            )
            raw_output = proc.stdout
            return self._parse_ping_output(raw_output, proc.returncode)
        except subprocess.TimeoutExpired:
            return {
                "target": self.target,
                "status": "TIMEOUT",
                "packets_transmitted": self.count,
                "packets_received": 0,
                "packet_loss_pct": 100.0,
                "rtt_min_ms": None,
                "rtt_avg_ms": None,
                "rtt_max_ms": None,
                "rtt_mdev_ms": None,
                "error": "Ping command timed out."
            }
        except Exception as e:
            return {
                "target": self.target,
                "status": "ERROR",
                "packets_transmitted": self.count,
                "packets_received": 0,
                "packet_loss_pct": 100.0,
                "rtt_min_ms": None,
                "rtt_avg_ms": None,
                "rtt_max_ms": None,
                "rtt_mdev_ms": None,
                "error": str(e)
            }

    def _parse_ping_output(self, output: str, returncode: int) -> Dict[str, Any]:
        """Parses stdout of standard ping utility."""
        transmitted = self.count
        received = 0
        loss_pct = 100.0

        # Loss parsing: e.g. "5 packets transmitted, 5 received, 0% packet loss"
        loss_match = re.search(r"(\d+)\s+(?:packets\s+)?transmitted,\s+(\d+)\s+(?:packets\s+)?received.*?(?:([0-9.]+)%\s+packet\s+loss)", output, re.IGNORECASE)
        if loss_match:
            transmitted = int(loss_match.group(1))
            received = int(loss_match.group(2))
            loss_pct = float(loss_match.group(3))

        # RTT parsing:
        # Linux: "rtt min/avg/max/mdev = 0.038/0.054/0.071/0.012 ms"
        # macOS: "round-trip min/avg/max/stddev = 0.038/0.054/0.071/0.012 ms"
        rtt_match = re.search(r"(?:rtt|round-trip)\s+min/avg/max/(?:mdev|stddev)\s*=\s*([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+)\s*ms", output)

        min_ms, avg_ms, max_ms, mdev_ms = None, None, None, None
        if rtt_match:
            min_ms = float(rtt_match.group(1))
            avg_ms = float(rtt_match.group(2))
            max_ms = float(rtt_match.group(3))
            mdev_ms = float(rtt_match.group(4))

        status = "OK"
        if loss_pct > 0.0 or returncode != 0:
            status = "DEGRADED" if received > 0 else "UNREACHABLE"

        # If ICMP unreachable or sandboxed and tcp_port is provided, attempt TCP-SYN probe
        if status == "UNREACHABLE" and self.tcp_port is not None:
            tcp_result = self.run_tcp_syn_probe(self.tcp_port)
            if tcp_result.get("status") in ("OK", "DEGRADED"):
                return tcp_result

        return {
            "target": self.target,
            "status": status,
            "probe_type": "ICMP",
            "packets_transmitted": transmitted,
            "packets_received": received,
            "packet_loss_pct": loss_pct,
            "rtt_min_ms": min_ms,
            "rtt_avg_ms": avg_ms,
            "rtt_max_ms": max_ms,
            "rtt_mdev_ms": mdev_ms,
            "raw_output": output.strip()
        }
