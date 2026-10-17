from __future__ import annotations

import datetime as dt
import unittest

from vision_archive_probe import pending_jobs


class VisionArchiveProbeTests(unittest.TestCase):
    def test_resume_retries_errors_but_not_http_responses(self):
        day = dt.date(2026, 1, 1)
        report = {"datasets": {"metrics": {"AAAUSDT": {
            day.isoformat(): {"status": 404},
        }, "BBBUSDT": {
            day.isoformat(): {"status": "ERROR", "error": "timeout"},
        }}}}
        jobs = list(pending_jobs(report, ("metrics",), ["AAAUSDT", "BBBUSDT"], [day]))
        self.assertEqual(jobs, [("metrics", "BBBUSDT", day)])


if __name__ == "__main__":
    unittest.main()
