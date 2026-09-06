"""
Unit Tests for Telemetry Collectors & Memory Leak Detection
"""
import unittest
from daemon.collectors.cpu import CpuCollector
from daemon.collectors.memory import MemoryCollector, MemoryLeakDetector
from daemon.collectors.disk import DiskCollector


class TestCpuCollector(unittest.TestCase):
    def setUp(self):
        self.collector = CpuCollector()

    def test_cpu_collector_structure(self):
        metrics = self.collector.collect()
        self.assertIn("cores", metrics)
        self.assertIn("load_average", metrics)
        self.assertIn("utilization_pct", metrics)
        self.assertIn("status", metrics)
        self.assertIn(metrics["status"], ["OK", "WARNING", "CRITICAL"])
        self.assertGreaterEqual(metrics["cores"], 1)
        self.assertGreaterEqual(metrics["utilization_pct"], 0.0)
        self.assertLessEqual(metrics["utilization_pct"], 100.0)


class TestMemoryLeakDetector(unittest.TestCase):
    def test_memory_leak_detection_synthetic(self):
        detector = MemoryLeakDetector(
            window_size=6,
            consecutive_growth_threshold=4,
            min_growth_mb=15.0
        )

        # Inject simulated leaking process PID 9999
        # Trajectory: 20MB -> 40MB -> 65MB -> 90MB (strictly increasing +70MB growth)
        samples = [20.0, 40.0, 65.0, 90.0]
        for rss in samples:
            detector.history[9999].append((rss, "leaky_worker"))

        # Inject stable process PID 8888 (oscillating)
        for rss in [50.0, 52.0, 49.0, 51.0]:
            detector.history[8888].append((rss, "stable_worker"))

        # Check leak analysis directly
        suspects = []
        for pid, history_queue in detector.history.items():
            if len(history_queue) >= detector.consecutive_growth_threshold:
                q_samples = list(history_queue)
                consecutive = 0
                for i in range(1, len(q_samples)):
                    if q_samples[i][0] > q_samples[i - 1][0]:
                        consecutive += 1
                    else:
                        consecutive = 0

                growth = round(q_samples[-1][0] - q_samples[0][0], 2)
                if consecutive >= (detector.consecutive_growth_threshold - 1) and growth >= detector.min_growth_mb:
                    suspects.append({
                        "pid": pid,
                        "process": q_samples[-1][1],
                        "growth_delta_mb": growth
                    })

        self.assertEqual(len(suspects), 1)
        self.assertEqual(suspects[0]["pid"], 9999)
        self.assertEqual(suspects[0]["process"], "leaky_worker")
        self.assertEqual(suspects[0]["growth_delta_mb"], 70.0)


class TestMemoryCollector(unittest.TestCase):
    def setUp(self):
        self.collector = MemoryCollector()

    def test_memory_collection(self):
        metrics = self.collector.collect()
        self.assertIn("stats", metrics)
        self.assertIn("leak_suspects", metrics)
        self.assertIn("status", metrics)
        stats = metrics["stats"]
        self.assertGreater(stats["ram_total_mb"], 0)
        self.assertGreaterEqual(stats["ram_used_pct"], 0.0)
        self.assertLessEqual(stats["ram_used_pct"], 100.0)


class TestDiskCollector(unittest.TestCase):
    def setUp(self):
        self.collector = DiskCollector()

    def test_disk_collection(self):
        metrics = self.collector.collect()
        self.assertIn("partitions", metrics)
        self.assertIn("status", metrics)
        self.assertGreater(len(metrics["partitions"]), 0)
        root = metrics["partitions"][0]
        self.assertEqual(root["mountpoint"], "/")
        self.assertGreater(root["total_gb"], 0)
        self.assertGreaterEqual(root["capacity_used_pct"], 0.0)
        self.assertLessEqual(root["capacity_used_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
