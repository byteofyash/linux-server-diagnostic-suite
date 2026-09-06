"""
iperf3 Benchmarking Automation Runner
Executes TCP throughput and UDP jitter/packet-loss diagnostics against target servers.
Parses native iperf3 JSON telemetry for network performance analysis.
"""
import os
import json
import shutil
import subprocess
from typing import Dict, Any, Optional


class IperfBenchmarkRunner:
    def __init__(self, target: str = "127.0.0.1", port: int = 5201):
        self.target = target
        self.port = port
        self.iperf_bin = shutil.which("iperf3")

    def is_available(self) -> bool:
        """Checks if iperf3 binary is available in PATH."""
        return self.iperf_bin is not None

    def run_tcp_benchmark(
        self,
        duration_sec: int = 5,
        parallel_streams: int = 2,
        reverse: bool = False
    ) -> Dict[str, Any]:
        """
        Runs TCP throughput benchmark and parses sender/receiver bitrates,
        retransmissions, and congestion metrics.
        """
        if not self.is_available():
            return {
                "protocol": "TCP",
                "status": "UNAVAILABLE",
                "error": "iperf3 binary not found in system PATH. Install via 'apt install iperf3' or 'brew install iperf3'."
            }

        cmd = [
            self.iperf_bin,
            "-c", self.target,
            "-p", str(self.port),
            "-t", str(duration_sec),
            "-P", str(parallel_streams),
            "-J" # JSON output
        ]
        if reverse:
            cmd.append("-R")

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=duration_sec + 10
            )

            if proc.returncode != 0:
                # Try parsing error from json or stderr
                err_msg = proc.stderr.strip()
                try:
                    data = json.loads(proc.stdout)
                    err_msg = data.get("error", err_msg)
                except Exception:
                    pass
                return {
                    "protocol": "TCP",
                    "status": "ERROR",
                    "target": self.target,
                    "error": err_msg or "Failed to connect to iperf3 server."
                }

            return self.parse_tcp_json(proc.stdout)

        except subprocess.TimeoutExpired:
            return {
                "protocol": "TCP",
                "status": "TIMEOUT",
                "target": self.target,
                "error": "Benchmark timed out."
            }
        except Exception as e:
            return {
                "protocol": "TCP",
                "status": "ERROR",
                "target": self.target,
                "error": str(e)
            }

    def parse_tcp_json(self, raw_json: str) -> Dict[str, Any]:
        """Extracts structured performance metrics from iperf3 JSON output."""
        try:
            data = json.loads(raw_json)
            end = data.get("end", {})
            sum_sent = end.get("sum_sent", {})
            sum_received = end.get("sum_received", {})

            sender_bps = sum_sent.get("bits_per_second", 0.0)
            receiver_bps = sum_received.get("bits_per_second", 0.0)
            retransmits = sum_sent.get("retransmits", 0)
            bytes_sent = sum_sent.get("bytes", 0)
            bytes_received = sum_received.get("bytes", 0)

            sender_mbps = round(sender_bps / 1_000_000.0, 2)
            receiver_mbps = round(receiver_bps / 1_000_000.0, 2)

            return {
                "protocol": "TCP",
                "status": "SUCCESS",
                "target": self.target,
                "port": self.port,
                "sender_mbps": sender_mbps,
                "receiver_mbps": receiver_mbps,
                "total_bytes_sent_mb": round(bytes_sent / (1024 * 1024), 2),
                "total_bytes_received_mb": round(bytes_received / (1024 * 1024), 2),
                "retransmits": retransmits,
                "streams": len(data.get("intervals", [{}])[0].get("streams", [])) if data.get("intervals") else 1
            }
        except Exception as e:
            return {
                "protocol": "TCP",
                "status": "PARSE_ERROR",
                "error": f"Failed to parse iperf3 JSON output: {e}"
            }

    def run_udp_benchmark(
        self,
        bandwidth: str = "50M",
        duration_sec: int = 5
    ) -> Dict[str, Any]:
        """
        Runs UDP benchmark measuring packet loss percentage and jitter.
        """
        if not self.is_available():
            return {
                "protocol": "UDP",
                "status": "UNAVAILABLE",
                "error": "iperf3 binary not found in PATH."
            }

        cmd = [
            self.iperf_bin,
            "-c", self.target,
            "-p", str(self.port),
            "-u", # UDP mode
            "-b", bandwidth,
            "-t", str(duration_sec),
            "-J"
        ]

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=duration_sec + 10
            )

            if proc.returncode != 0:
                err_msg = proc.stderr.strip()
                try:
                    data = json.loads(proc.stdout)
                    err_msg = data.get("error", err_msg)
                except Exception:
                    pass
                return {
                    "protocol": "UDP",
                    "status": "ERROR",
                    "target": self.target,
                    "error": err_msg or "Failed to connect to iperf3 server."
                }

            return self.parse_udp_json(proc.stdout)

        except Exception as e:
            return {
                "protocol": "UDP",
                "status": "ERROR",
                "target": self.target,
                "error": str(e)
            }

    def parse_udp_json(self, raw_json: str) -> Dict[str, Any]:
        """Parses UDP throughput, jitter, and loss from iperf3 JSON output."""
        try:
            data = json.loads(raw_json)
            end = data.get("end", {})
            sum_data = end.get("sum", {})

            jitter_ms = round(sum_data.get("jitter_ms", 0.0), 3)
            lost_packets = sum_data.get("lost_packets", 0)
            total_packets = sum_data.get("packets", 0)
            lost_percent = round(sum_data.get("lost_percent", 0.0), 2)
            bps = sum_data.get("bits_per_second", 0.0)

            return {
                "protocol": "UDP",
                "status": "SUCCESS",
                "target": self.target,
                "port": self.port,
                "throughput_mbps": round(bps / 1_000_000.0, 2),
                "jitter_ms": jitter_ms,
                "lost_packets": lost_packets,
                "total_packets": total_packets,
                "packet_loss_pct": lost_percent
            }
        except Exception as e:
            return {
                "protocol": "UDP",
                "status": "PARSE_ERROR",
                "error": f"Failed to parse iperf3 UDP JSON: {e}"
            }
