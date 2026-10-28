from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from monitor import TARGETS, import_history, probe, snapshot


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
        self.assertEqual(dashboard["uptime"], 50)
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

    @patch("monitor.time.sleep")
    @patch("monitor.urlopen", side_effect=OSError("network down"))
    def test_probe_failure_is_recorded(self, request, sleep):
        self.assertFalse(probe("dashboard")[0])
        self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
