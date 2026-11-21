"""Run with: python3 -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import health_report  # noqa: E402  pylint: disable=wrong-import-position
import node_health  # noqa: E402  pylint: disable=wrong-import-position

MDSTAT_HEALTHY = """Personalities : [raid1]
md1 : active raid1 nvme1n1p2[1] nvme0n1p2[0]
      1046528 blocks super 1.2 [2/2] [UU]

md2 : active raid1 nvme1n1p3[1] nvme0n1p3[0]
      498923840 blocks super 1.2 [2/2] [UU]
      bitmap: 2/4 pages [8KB], 65536KB chunk

unused devices: <none>
"""

MDSTAT_DEGRADED = """Personalities : [raid1]
md1 : active raid1 nvme0n1p2[0]
      1046528 blocks super 1.2 [2/1] [U_]

md2 : active raid1 nvme1n1p3[2] nvme0n1p3[0]
      498923840 blocks super 1.2 [2/1] [U_]
      [=>...................]  recovery =  8.5% (42450560/498923840) finish=37.9min speed=200320K/sec

md3 : active raid1 sdb1[1](F) sda1[0]
      1046528 blocks super 1.2 [2/1] [U_]

unused devices: <none>
"""


class MdstatTest(unittest.TestCase):
    def test_healthy(self):
        arrays = node_health.parse_mdstat(MDSTAT_HEALTHY)
        self.assertEqual([a["name"] for a in arrays], ["md1", "md2"])
        self.assertFalse(any(a["degraded"] for a in arrays))
        self.assertEqual(arrays[1]["state"], "UU")

    def test_degraded(self):
        arrays = node_health.parse_mdstat(MDSTAT_DEGRADED)
        self.assertTrue(all(a["degraded"] for a in arrays))
        self.assertEqual(arrays[1]["resync"], "recovery 8.5%")


class SmartTest(unittest.TestCase):
    def test_healthy_nvme(self):
        result = node_health.evaluate_smart({
            "device": {"name": "/dev/nvme0n1"},
            "smart_status": {"passed": True},
            "nvme_smart_health_information_log": {
                "critical_warning": 0, "media_errors": 0, "percentage_used": 3,
                "available_spare": 100, "available_spare_threshold": 10,
            },
        })
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["wear_percent"], 3)

    def test_failing_nvme(self):
        result = node_health.evaluate_smart({
            "smart_status": {"passed": False},
            "nvme_smart_health_information_log": {"critical_warning": 4, "media_errors": 12, "percentage_used": 97},
        })
        self.assertEqual(len(result["problems"]), 4)

    def test_ata_reallocated(self):
        result = node_health.evaluate_smart({
            "smart_status": {"passed": True},
            "ata_smart_attributes": {"table": [
                {"id": 5, "raw": {"value": 8}},
                {"id": 9, "raw": {"value": 30000}},
                {"id": 197, "raw": {"value": 0}},
            ]},
        })
        self.assertEqual(result["problems"], ["8 reallocated sectors (attribute 5)"])


class ClusterTest(unittest.TestCase):
    def test_pods(self):
        pods = "\n".join([
            "kube-system cilium-abc Running true",
            "kube-system job-xyz Succeeded false",
            "default crash Running true,false",
            "default pending Pending <none>",
        ])
        problems = health_report.cluster_problems({"items": []}, pods)
        self.assertEqual(len(problems), 2)


if __name__ == "__main__":
    unittest.main()
