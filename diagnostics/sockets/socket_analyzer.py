"""
Socket State and Connection Diagnostic Analyzer
Inspects kernel socket tables (via ss / netstat / /proc/net), parses TCP connection states,
and diagnoses socket leaks, queue backpressure, and port exhaustion risks.
"""
import shutil
import subprocess
from collections import Counter
from typing import Dict, Any, List, Optional


class SocketAnalyzer:
    def __init__(self):
        self.has_ss = shutil.which("ss") is not None
        self.has_netstat = shutil.which("netstat") is not None

    def analyze(self) -> Dict[str, Any]:
        """
        Executes socket inspection and evaluates socket health metrics.
        """
        if self.has_ss:
            return self._analyze_via_ss()
        elif self.has_netstat:
            return self._analyze_via_netstat()
        else:
            return {
                "status": "UNAVAILABLE",
                "error": "Neither 'ss' nor 'netstat' is installed on this system."
            }

    def _analyze_via_ss(self) -> Dict[str, Any]:
        """
        Parses `ss -t -a -n` output (TCP, all sockets, numeric).
        """
        try:
            # -t = TCP, -a = all (listening and non-listening), -n = numeric, -i = internal TCP info
            proc = subprocess.run(
                ["ss", "-t", "-a", "-n"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=5
            )
            lines = proc.stdout.strip().split("\n")
            if len(lines) < 2:
                return {"status": "EMPTY", "total_sockets": 0, "states": {}}

            # Header: State Recv-Q Send-Q Local Address:Port Peer Address:Port
            state_counts: Counter = Counter()
            high_recv_q_sockets = []
            high_send_q_sockets = []
            close_wait_sockets = []
            active_sockets = []

            for line in lines[1:]:
                parts = line.split()
                if not parts:
                    continue

                state = parts[0].upper()
                # Normalize state names
                if state == "ESTAB":
                    state = "ESTABLISHED"
                elif state == "UNCONN":
                    state = "UNCONNECTED"

                state_counts[state] += 1

                try:
                    recv_q = int(parts[1])
                    send_q = int(parts[2])
                    local = parts[3] if len(parts) > 3 else "unknown"
                    peer = parts[4] if len(parts) > 4 else "unknown"

                    sock_entry = {
                        "state": state,
                        "recv_q": recv_q,
                        "send_q": send_q,
                        "local": local,
                        "peer": peer
                    }

                    active_sockets.append(sock_entry)

                    if recv_q > 1024:
                        high_recv_q_sockets.append(sock_entry)
                    if send_q > 1024:
                        high_send_q_sockets.append(sock_entry)
                    if state == "CLOSE_WAIT":
                        close_wait_sockets.append(sock_entry)
                except (ValueError, IndexError):
                    continue

            return self._evaluate_health(
                state_counts,
                high_recv_q_sockets,
                high_send_q_sockets,
                close_wait_sockets,
                active_sockets
            )

        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    def _analyze_via_netstat(self) -> Dict[str, Any]:
        """Fallback socket analysis via netstat."""
        try:
            proc = subprocess.run(
                ["netstat", "-an", "-p", "tcp"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=5
            )
            state_counts: Counter = Counter()
            active_sockets = []
            close_wait_sockets = []

            for line in proc.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 6 and parts[0].startswith("tcp"):
                    state = parts[-1].upper()
                    recv_q = int(parts[1]) if parts[1].isdigit() else 0
                    send_q = int(parts[2]) if parts[2].isdigit() else 0
                    local = parts[3]
                    peer = parts[4]

                    state_counts[state] += 1
                    sock_entry = {
                        "state": state,
                        "recv_q": recv_q,
                        "send_q": send_q,
                        "local": local,
                        "peer": peer
                    }
                    active_sockets.append(sock_entry)
                    if state == "CLOSE_WAIT":
                        close_wait_sockets.append(sock_entry)

            return self._evaluate_health(
                state_counts,
                [],
                [],
                close_wait_sockets,
                active_sockets
            )
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    def _evaluate_health(
        self,
        state_counts: Counter,
        high_recv_q: List[Dict[str, Any]],
        high_send_q: List[Dict[str, Any]],
        close_wait: List[Dict[str, Any]],
        all_sockets: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Diagnoses socket leaks, ephemeral port exhaustion, and buffer backpressure."""
        diagnostics = []
        status = "HEALTHY"

        total_tcp = sum(state_counts.values())
        time_wait_count = state_counts.get("TIME_WAIT", 0)
        close_wait_count = state_counts.get("CLOSE_WAIT", 0)
        syn_sent_count = state_counts.get("SYN_SENT", 0)

        # 1. CLOSE_WAIT leak detection: Remote peer initiated close, local app failed to close()
        if close_wait_count > 10:
            status = "WARNING"
            diagnostics.append(
                f"POTENTIAL SOCKET LEAK: {close_wait_count} sockets lingering in CLOSE_WAIT. "
                "Local application is not properly invoking close() on remote-terminated sockets."
            )

        # 2. TIME_WAIT accumulation: High turnover of short-lived connections
        if time_wait_count > 2000:
            status = "WARNING"
            diagnostics.append(
                f"HIGH TIME_WAIT ACCUMULATION: {time_wait_count} sockets in TIME_WAIT. "
                "Risk of ephemeral port exhaustion. Consider enabling TCP TW reuse or connection pooling."
            )

        # 3. SYN_SENT accumulation: Outgoing connections failing or being firewalled
        if syn_sent_count > 50:
            status = "WARNING"
            diagnostics.append(
                f"SYN_SENT STALL: {syn_sent_count} sockets stuck in SYN_SENT. "
                "Outbound packets may be dropped by remote firewalls or destination host down."
            )

        # 4. Socket buffer queue backpressure
        if high_recv_q:
            diagnostics.append(
                f"BUFFER BACKPRESSURE: {len(high_recv_q)} sockets have Recv-Q > 1024 bytes. "
                "Local receiver application is lagging behind network ingest rate."
            )
        if high_send_q:
            diagnostics.append(
                f"TRANSMIT BACKPRESSURE: {len(high_send_q)} sockets have Send-Q > 1024 bytes. "
                "Remote peer or network path is throttling transmission throughput."
            )

        return {
            "status": status,
            "total_tcp_sockets": total_tcp,
            "state_breakdown": dict(state_counts),
            "diagnostics": diagnostics,
            "backpressure": {
                "high_recv_q_count": len(high_recv_q),
                "high_send_q_count": len(high_send_q),
                "close_wait_count": close_wait_count
            },
            "sample_sockets": all_sockets[:10]
        }
