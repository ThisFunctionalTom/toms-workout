from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


sys.modules.setdefault("garminconnect", types.SimpleNamespace(Garmin=object))
SCRIPT = Path(__file__).with_name("upload_latest_garmin.py")
spec = importlib.util.spec_from_file_location("upload_latest_garmin", SCRIPT)
uploader = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = uploader
spec.loader.exec_module(uploader)


class ActivityMatchTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 18, 11, 18, tzinfo=timezone.utc)
        self.entry = {"name": "Week 1 - Day 3 - Bench + Squat", "start": self.start.isoformat()}

    def activity(self, name, start):
        return {"activityName": name, "startTimeGMT": start.strftime("%Y-%m-%d %H:%M:%S")}

    def test_matches_display_name_within_sixty_seconds(self):
        activities = [self.activity(self.entry["name"], self.start + timedelta(seconds=60))]
        self.assertIsNotNone(uploader.require_unique_match(self.entry, activities))

    def test_does_not_match_different_title(self):
        activities = [self.activity("Different workout", self.start)]
        self.assertIsNone(uploader.require_unique_match(self.entry, activities))

    def test_does_not_match_outside_sixty_seconds(self):
        activities = [self.activity(self.entry["name"], self.start + timedelta(seconds=61))]
        self.assertIsNone(uploader.require_unique_match(self.entry, activities))

    def test_does_not_match_legacy_id_suffixed_title(self):
        legacy_title = f"{self.entry['name']} [Liftosaur ID 12345]"
        activities = [self.activity(legacy_title, self.start)]
        self.assertIsNone(uploader.require_unique_match(self.entry, activities))

    def test_rejects_ambiguous_activity_match(self):
        activities = [
            self.activity(self.entry["name"], self.start),
            self.activity(self.entry["name"], self.start + timedelta(seconds=20)),
        ]
        with self.assertRaisesRegex(ValueError, "Multiple Garmin activities match"):
            uploader.require_unique_match(self.entry, activities)

    def test_parses_garmin_utc_timestamp(self):
        self.assertEqual(
            self.start,
            uploader.parse_timestamp("2026-10-18T11:18:00Z"),
        )
        self.assertIsNone(uploader.activity_key({"activityName": "Workout", "startTimeLocal": "2026-10-18 11:18:00"}))


if __name__ == "__main__":
    unittest.main()
