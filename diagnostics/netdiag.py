#!/usr/bin/env python3
"""
netdiag: Network Diagnostic & Benchmarking CLI Suite
Orchestrates latency probes, iperf3 throughput tests, and TCP socket state diagnosis.
"""
import os
import sys
import json
import argparse
from typing import Optional

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from latency.probe import LatencyProbe
from benchmarks.iperf_runner import IperfBenchmarkRunner
from sockets.socket_analyzer import SocketAnalyzer
from reporter import DiagnosticReporter


def main():
    parser = argparse.ArgumentParser(
        description="netdiag: Linux Network Latency, Throughput & Socket Diagnostic Suite"
    )
    parser.add_argument("--target", "-t", type=str, default="127.0.0.1", help="Target host / IP (default: 127.0.0.1)")
    parser.add_argument("--port", "-p", type=int, default=5201, help="iperf3 port (default: 5201)")
    parser.add_argument("--duration", "-d", type=int, default=5, help="Test duration in seconds (default: 5)")
    parser.add_argument("--streams", "-s", type=int, default=2, help="Parallel streams for TCP (default: 2)")
    parser.add_argument("--udp-bandwidth", "-b", type=str, default="50M", help="Target UDP bandwidth (default: 50M)")
    parser.add_argument("--tcp", action="store_true", help="Run TCP throughput benchmark")
    parser.add_argument("--udp", action="store_true", help="Run UDP jitter & packet loss benchmark")
    parser.add_argument("--sockets", action="store_true", help="Inspect local kernel socket states & leaks")
    parser.add_argument("--all", action="store_true", help="Execute complete diagnostic suite (Latency + TCP + UDP + Sockets)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--export", type=str, default=None, help="Export audit report to Markdown file")

    args = parser.parse_args()

    # Default to --all if no specific test flag is passed
    if not (args.tcp or args.udp or args.sockets or args.all):
        args.all = True

    run_tcp = args.tcp or args.all
    run_udp = args.udp or args.all
    run_sockets = args.sockets or args.all

    # 1. Latency Probe (ICMP with fallback to TCP SYN on the target port)
    probe = LatencyProbe(target=args.target, count=5, tcp_port=args.port)
    latency_res = probe.run()

    # 2. iperf3 Benchmarks
    iperf_runner = IperfBenchmarkRunner(target=args.target, port=args.port)
    tcp_res = None
    udp_res = None

    if run_tcp:
        tcp_res = iperf_runner.run_tcp_benchmark(
            duration_sec=args.duration,
            parallel_streams=args.streams
        )

    if run_udp:
        udp_res = iperf_runner.run_udp_benchmark(
            bandwidth=args.udp_bandwidth,
            duration_sec=args.duration
        )

    # 3. Socket Analysis
    socket_res = {}
    if run_sockets:
        sock_analyzer = SocketAnalyzer()
        socket_res = sock_analyzer.analyze()

    # Consolidated Results
    results = {
        "target": args.target,
        "latency": latency_res,
        "iperf_tcp": tcp_res,
        "iperf_udp": udp_res,
        "sockets": socket_res
    }

    if args.json:
        print(json.dumps(results, indent=2))
        sys.exit(0)

    # Terminal rendering
    DiagnosticReporter.print_summary(
        latency_data=latency_res,
        iperf_tcp=tcp_res,
        iperf_udp=udp_res,
        socket_data=socket_res
    )

    if args.export:
        DiagnosticReporter.export_markdown(
            filepath=args.export,
            latency_data=latency_res,
            iperf_tcp=tcp_res,
            iperf_udp=udp_res,
            socket_data=socket_res
        )
        print(f"[INFO] Diagnostic audit report exported to: {args.export}\n")


if __name__ == "__main__":
    main()
