"""
Unit Tests for Socket Analyzer & Leak Diagnosis
"""
import unittest
from collections import Counter
from diagnostics.sockets.socket_analyzer import SocketAnalyzer


class TestSocketAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = SocketAnalyzer()

    def test_evaluate_health_clean(self):
        counts = Counter({"ESTABLISHED": 15, "LISTEN": 5, "TIME_WAIT": 10})
        res = self.analyzer._evaluate_health(
            state_counts=counts,
            high_recv_q=[],
            high_send_q=[],
            close_wait=[],
            all_sockets=[]
        )
        self.assertEqual(res["status"], "HEALTHY")
        self.assertEqual(len(res["diagnostics"]), 0)
        self.assertEqual(res["total_tcp_sockets"], 30)

    def test_evaluate_health_close_wait_leak(self):
        # Trigger socket leak condition (> 10 CLOSE_WAIT)
        counts = Counter({"CLOSE_WAIT": 25, "ESTABLISHED": 10})
        close_wait_mocks = [{"state": "CLOSE_WAIT", "local": "127.0.0.1:8080", "peer": "127.0.0.1:54321"}] * 25
        res = self.analyzer._evaluate_health(
            state_counts=counts,
            high_recv_q=[],
            high_send_q=[],
            close_wait=close_wait_mocks,
            all_sockets=[]
        )
        self.assertEqual(res["status"], "WARNING")
        self.assertTrue(any("POTENTIAL SOCKET LEAK" in d for d in res["diagnostics"]))

    def test_evaluate_health_time_wait_exhaustion(self):
        # Trigger high TIME_WAIT (> 2000)
        counts = Counter({"TIME_WAIT": 3500, "ESTABLISHED": 50})
        res = self.analyzer._evaluate_health(
            state_counts=counts,
            high_recv_q=[],
            high_send_q=[],
            close_wait=[],
            all_sockets=[]
        )
        self.assertEqual(res["status"], "WARNING")
        self.assertTrue(any("HIGH TIME_WAIT ACCUMULATION" in d for d in res["diagnostics"]))

    def test_evaluate_health_buffer_backpressure(self):
        counts = Counter({"ESTABLISHED": 10})
        high_recv = [{"state": "ESTABLISHED", "recv_q": 4096, "send_q": 0, "local": "1.1.1.1", "peer": "2.2.2.2"}]
        res = self.analyzer._evaluate_health(
            state_counts=counts,
            high_recv_q=high_recv,
            high_send_q=[],
            close_wait=[],
            all_sockets=[]
        )
        self.assertTrue(any("BUFFER BACKPRESSURE" in d for d in res["diagnostics"]))


if __name__ == "__main__":
    unittest.main()
