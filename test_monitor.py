from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from monitor import TARGETS, history_uptime, import_history, probe, snapshot


class MonitorTests(unittest.TestCase):
    def test_outage_recovery_and_missing_days(self):
        state = {}
        now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
        results = {key: (True, 10) for key in TARGETS}
        results["dashboard"] = (False, 20)
        first = snapshot(state, results, now, [])
        dashboard = first["components"][0]
        self.assertFalse(dashboard["operational"])
        self.assertEqual(dashboard["days"][-1]["outage_minutes"], 5)
        self.assertIsNone(dashboard["days"][0]["uptime"])
        results["dashboard"] = (True, 10)
        second = snapshot(state, results, now + timedelta(minutes=30), [])
        dashboard = second["components"][0]
        self.assertTrue(dashboard["operational"])
        self.assertLess(dashboard["uptime"], 100)
        self.assertGreater(dashboard["uptime"], 99)
        self.assertEqual(dashboard["days"][-1]["outage_minutes"], 5)

    def test_retention_and_tehran_midnight(self):
        state = {"dashboard": {"2025-01-01": {"checks": 100, "up": 0}}}
        now = datetime(2026, 10, 28, 21, tzinfo=timezone.utc)
        data = snapshot(state, {k: (True, 1) for k in TARGETS}, now, [])
        self.assertEqual(data["components"][0]["days"][-1]["date"], "2026-10-29")
        self.assertNotIn("2025-01-01", state["dashboard"])

    def test_import_public_history(self):
        state = import_history({"components": [{"key": "dns", "days": [
            {"date": "2026-10-27", "checks": 100, "uptime": 97, "outage_minutes": 3}
        ]}]})
        self.assertEqual(state["dns"]["2026-10-27"]["up"], 97)

    def test_declared_incident_matches_original_hourly_uptime(self):
        now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
        incident = {"impact": "major", "components": ["k8s_gateway"],
                    "started_at": "2026-10-26T18:53:24+00:00",
                    "resolved_at": "2026-10-26T22:36:04+00:00"}
        self.assertAlmostEqual(history_uptime("k8s_gateway", now, {}, [], [incident]),
                               100 * (2152 - 5) / 2152)
        self.assertEqual(history_uptime("dashboard", now, {}, [], [incident]), 100)

    def test_cluster_is_unknown_when_source_is_unavailable(self):
        now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
        results = {key: (True, 10) for key in TARGETS}
        results["k8s_cluster"] = (None, 0)
        data = snapshot({}, results, now, [])
        self.assertEqual([c["key"] for c in data["components"]],
                         ["dashboard", "k8s_gateway", "k8s_cluster", "dns"])
        self.assertIsNone(data["components"][2]["operational"])

    @patch("monitor.time.sleep")
    @patch("monitor.urlopen", side_effect=OSError("network down"))
    def test_probe_failure_is_recorded(self, request, sleep):
        self.assertFalse(probe("dashboard")[0])
        self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
