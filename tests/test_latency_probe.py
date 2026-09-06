"""
Unit Tests for Latency & Packet Loss Probe
"""
import unittest
from diagnostics.latency.probe import LatencyProbe


class TestLatencyProbe(unittest.TestCase):
    def setUp(self):
        self.probe = LatencyProbe(target="127.0.0.1", count=4)

    def test_parse_linux_ping_output(self):
        linux_output = """
        PING 127.0.0.1 (127.0.0.1) 56(84) bytes of data.
        64 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time=0.038 ms
        64 bytes from 127.0.0.1: icmp_seq=2 ttl=64 time=0.045 ms
        64 bytes from 127.0.0.1: icmp_seq=3 ttl=64 time=0.042 ms
        64 bytes from 127.0.0.1: icmp_seq=4 ttl=64 time=0.040 ms

        --- 127.0.0.1 ping statistics ---
        4 packets transmitted, 4 received, 0% packet loss, time 3072ms
        rtt min/avg/max/mdev = 0.038/0.041/0.045/0.003 ms
        """
        parsed = self.probe._parse_ping_output(linux_output, returncode=0)
        self.assertEqual(parsed["status"], "OK")
        self.assertEqual(parsed["packets_transmitted"], 4)
        self.assertEqual(parsed["packets_received"], 4)
        self.assertEqual(parsed["packet_loss_pct"], 0.0)
        self.assertEqual(parsed["rtt_min_ms"], 0.038)
        self.assertEqual(parsed["rtt_avg_ms"], 0.041)
        self.assertEqual(parsed["rtt_max_ms"], 0.045)
        self.assertEqual(parsed["rtt_mdev_ms"], 0.003)

    def test_parse_packet_loss(self):
        degraded_output = """
        --- 192.168.56.10 ping statistics ---
        10 packets transmitted, 7 received, 30.0% packet loss
        round-trip min/avg/max/stddev = 1.201/2.450/4.110/0.820 ms
        """
        parsed = self.probe._parse_ping_output(degraded_output, returncode=0)
        self.assertEqual(parsed["status"], "DEGRADED")
        self.assertEqual(parsed["packet_loss_pct"], 30.0)
        self.assertEqual(parsed["packets_transmitted"], 10)
        self.assertEqual(parsed["packets_received"], 7)


if __name__ == "__main__":
    unittest.main()
