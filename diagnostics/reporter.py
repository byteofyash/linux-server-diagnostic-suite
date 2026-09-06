"""
Network Diagnostic & Benchmark Reporter
Renders terminal ASCII tables and exports structured Markdown / JSON audit reports.
"""
import os
import json
import time
from typing import Dict, Any, List, Optional


class DiagnosticReporter:
    @staticmethod
    def render_table(headers: List[str], rows: List[List[Any]]) -> str:
        """Renders clean ASCII table without external dependencies."""
        if not rows:
            return ""

        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, val in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(val)))

        # Format rows
        sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
        head_line = "| " + " | ".join(f"{h:<{w}}" for h, w in zip(headers, col_widths)) + " |"

        lines = [sep, head_line, sep]
        for row in rows:
            line = "| " + " | ".join(f"{str(val):<{w}}" for val, w in zip(row, col_widths)) + " |"
            lines.append(line)
        lines.append(sep)

        return "\n".join(lines)

    @classmethod
    def print_summary(
        cls,
        latency_data: Dict[str, Any],
        iperf_tcp: Optional[Dict[str, Any]],
        iperf_udp: Optional[Dict[str, Any]],
        socket_data: Dict[str, Any]
    ):
        """Prints a comprehensive, colorized terminal diagnostic summary."""
        cyan = "\033[0;36m"
        green = "\033[0;32m"
        yellow = "\033[1;33m"
        red = "\033[0;31m"
        bold = "\033[1m"
        reset = "\033[0m"

        print(f"\n{bold}{cyan}========================================================================{reset}")
        print(f"{bold}{cyan}       LINUX SERVER NETWORK DIAGNOSTIC & BENCHMARK REPORT               {reset}")
        print(f"{bold}{cyan}========================================================================{reset}\n")

        # 1. Latency & ICMP Probe
        print(f"{bold}[1] Latency & Packet Loss Profile (Target: {latency_data.get('target', 'N/A')}){reset}")
        loss = latency_data.get("packet_loss_pct", 0.0)
        loss_color = green if loss == 0.0 else (yellow if loss < 5.0 else red)

        lat_headers = ["Metric", "Value", "Unit"]
        lat_rows = [
            ["Status", latency_data.get("status", "N/A"), "-"],
            ["Packets Transmitted", latency_data.get("packets_transmitted", 0), "pkts"],
            ["Packets Received", latency_data.get("packets_received", 0), "pkts"],
            ["Packet Loss", f"{loss_color}{loss}%{reset}", "%"],
            ["Min Round-Trip Time", latency_data.get("rtt_min_ms", "N/A"), "ms"],
            ["Avg Round-Trip Time", latency_data.get("rtt_avg_ms", "N/A"), "ms"],
            ["Max Round-Trip Time", latency_data.get("rtt_max_ms", "N/A"), "ms"],
            ["Jitter (mdev/stddev)", latency_data.get("rtt_mdev_ms", "N/A"), "ms"],
        ]
        print(cls.render_table(lat_headers, lat_rows))
        print()

        # 2. iperf3 Throughput & Bandwidth
        if iperf_tcp and iperf_tcp.get("status") == "SUCCESS":
            print(f"{bold}[2] iperf3 TCP Throughput Benchmark{reset}")
            tcp_headers = ["Metric", "Value", "Unit"]
            tcp_rows = [
                ["Sender Bitrate", iperf_tcp.get("sender_mbps", "N/A"), "Mbits/sec"],
                ["Receiver Bitrate", iperf_tcp.get("receiver_mbps", "N/A"), "Mbits/sec"],
                ["Total Transferred", iperf_tcp.get("total_bytes_sent_mb", "N/A"), "MBytes"],
                ["TCP Retransmissions", iperf_tcp.get("retransmits", 0), "retrans"],
                ["Parallel Streams", iperf_tcp.get("streams", 1), "streams"]
            ]
            print(cls.render_table(tcp_headers, tcp_rows))
            print()
        elif iperf_tcp:
            print(f"{bold}[2] iperf3 TCP Throughput:{reset} {yellow}{iperf_tcp.get('error', 'Skipped/Unavailable')}{reset}\n")

        # 3. iperf3 UDP Jitter & Packet Loss
        if iperf_udp and iperf_udp.get("status") == "SUCCESS":
            print(f"{bold}[3] iperf3 UDP Jitter & Packet Loss Benchmark{reset}")
            udp_headers = ["Metric", "Value", "Unit"]
            udp_rows = [
                ["Bandwidth Rate", iperf_udp.get("throughput_mbps", "N/A"), "Mbits/sec"],
                ["Jitter", iperf_udp.get("jitter_ms", "N/A"), "ms"],
                ["Lost Packets", iperf_udp.get("lost_packets", 0), "pkts"],
                ["Total Packets", iperf_udp.get("total_packets", 0), "pkts"],
                ["UDP Packet Loss", f"{iperf_udp.get('packet_loss_pct', 0.0)}%", "%"]
            ]
            print(cls.render_table(udp_headers, udp_rows))
            print()

        # 4. Socket State Analysis
        print(f"{bold}[4] Kernel Socket State & Leak Diagnostics{reset}")
        if socket_data.get("status") in ("HEALTHY", "WARNING"):
            states = socket_data.get("state_breakdown", {})
            sock_headers = ["TCP State", "Count", "Health Implication"]
            implications = {
                "ESTABLISHED": "Active connections communicating data",
                "LISTEN": "Daemon ports awaiting incoming handshakes",
                "TIME_WAIT": "Closed locally; awaiting socket timeout release",
                "CLOSE_WAIT": "Remote closed; application awaiting close()",
                "SYN_SENT": "Awaiting server SYN-ACK handshake",
                "SYN_RECV": "Awaiting client ACK handshake",
                "FIN_WAIT1": "Local closed; awaiting ACK/FIN",
                "FIN_WAIT2": "Local closed; awaiting remote FIN"
            }
            sock_rows = []
            for st, count in sorted(states.items(), key=lambda x: x[1], reverse=True):
                impl = implications.get(st, "Standard kernel TCP state")
                sock_rows.append([st, count, impl])
            print(cls.render_table(sock_headers, sock_rows))

            if socket_data.get("diagnostics"):
                print(f"\n{bold}Diagnostic Findings:{reset}")
                for diag in socket_data["diagnostics"]:
                    print(f"  {yellow}• {diag}{reset}")
            else:
                print(f"\n{green}✓ Socket tables healthy: No connection leaks or buffer backpressure detected.{reset}")
        else:
            print(f"{yellow}{socket_data.get('error', 'Socket data unavailable')}{reset}")

        print(f"\n{bold}{cyan}========================================================================{reset}\n")

    @classmethod
    def export_markdown(
        cls,
        filepath: str,
        latency_data: Dict[str, Any],
        iperf_tcp: Optional[Dict[str, Any]],
        iperf_udp: Optional[Dict[str, Any]],
        socket_data: Dict[str, Any]
    ):
        """Exports benchmark metrics into a Markdown audit document."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime())

        md = [
            "# Network Benchmark & Socket Diagnostic Audit Report",
            f"**Generated:** {timestamp}  ",
            f"**Target Node:** `{latency_data.get('target', 'localhost')}`  ",
            "",
            "## 1. Latency & ICMP Statistics",
            "| Metric | Value | Unit |",
            "| :--- | :--- | :--- |",
            f"| Status | {latency_data.get('status')} | - |",
            f"| Packet Loss | {latency_data.get('packet_loss_pct')}% | % |",
            f"| Min RTT | {latency_data.get('rtt_min_ms', 'N/A')} | ms |",
            f"| Avg RTT | {latency_data.get('rtt_avg_ms', 'N/A')} | ms |",
            f"| Max RTT | {latency_data.get('rtt_max_ms', 'N/A')} | ms |",
            f"| Jitter (mdev) | {latency_data.get('rtt_mdev_ms', 'N/A')} | ms |",
            "",
            "## 2. iperf3 Bandwidth & Throughput",
        ]

        if iperf_tcp and iperf_tcp.get("status") == "SUCCESS":
            md.extend([
                "### TCP Benchmark",
                "| Metric | Value |",
                "| :--- | :--- |",
                f"| Sender Bitrate | {iperf_tcp.get('sender_mbps')} Mbits/sec |",
                f"| Receiver Bitrate | {iperf_tcp.get('receiver_mbps')} Mbits/sec |",
                f"| Total Transferred | {iperf_tcp.get('total_bytes_sent_mb')} MB |",
                f"| Retransmissions | {iperf_tcp.get('retransmits')} |",
                ""
            ])

        if iperf_udp and iperf_udp.get("status") == "SUCCESS":
            md.extend([
                "### UDP Benchmark",
                "| Metric | Value |",
                "| :--- | :--- |",
                f"| Bandwidth Rate | {iperf_udp.get('throughput_mbps')} Mbits/sec |",
                f"| Jitter | {iperf_udp.get('jitter_ms')} ms |",
                f"| Packet Loss | {iperf_udp.get('packet_loss_pct')}% ({iperf_udp.get('lost_packets')} / {iperf_udp.get('total_packets')}) |",
                ""
            ])

        md.extend([
            "## 3. Kernel Socket State Distribution",
            "| State | Count |",
            "| :--- | :--- |"
        ])
        for st, count in socket_data.get("state_breakdown", {}).items():
            md.append(f"| {st} | {count} |")

        if socket_data.get("diagnostics"):
            md.extend(["", "### Diagnostic Warnings"])
            for d in socket_data["diagnostics"]:
                md.append(f"- **WARNING:** {d}")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
