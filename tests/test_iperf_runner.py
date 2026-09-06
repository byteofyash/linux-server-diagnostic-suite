"""
Unit Tests for iperf3 Benchmark Parsing
"""
import unittest
from diagnostics.benchmarks.iperf_runner import IperfBenchmarkRunner


class TestIperfRunner(unittest.TestCase):
    def setUp(self):
        self.runner = IperfBenchmarkRunner(target="127.0.0.1", port=5201)

    def test_parse_tcp_json(self):
        sample_json = """
        {
          "intervals": [{"streams": [{}, {}]}],
          "end": {
            "sum_sent": {
              "bits_per_second": 941000000.0,
              "bytes": 117625000,
              "retransmits": 3
            },
            "sum_received": {
              "bits_per_second": 939000000.0,
              "bytes": 117375000
            }
          }
        }
        """
        parsed = self.runner.parse_tcp_json(sample_json)
        self.assertEqual(parsed["status"], "SUCCESS")
        self.assertEqual(parsed["sender_mbps"], 941.0)
        self.assertEqual(parsed["receiver_mbps"], 939.0)
        self.assertEqual(parsed["retransmits"], 3)
        self.assertEqual(parsed["streams"], 2)

    def test_parse_udp_json(self):
        sample_json = """
        {
          "end": {
            "sum": {
              "bits_per_second": 50000000.0,
              "jitter_ms": 0.124,
              "lost_packets": 2,
              "packets": 1000,
              "lost_percent": 0.20
            }
          }
        }
        """
        parsed = self.runner.parse_udp_json(sample_json)
        self.assertEqual(parsed["status"], "SUCCESS")
        self.assertEqual(parsed["throughput_mbps"], 50.0)
        self.assertEqual(parsed["jitter_ms"], 0.124)
        self.assertEqual(parsed["lost_packets"], 2)
        self.assertEqual(parsed["total_packets"], 1000)
        self.assertEqual(parsed["packet_loss_pct"], 0.20)


if __name__ == "__main__":
    unittest.main()
