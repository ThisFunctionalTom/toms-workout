from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


sys.modules.setdefault("garminconnect", types.SimpleNamespace(Garmin=object))
SCRIPT = Path(__file__).with_name("upload_latest_garmin.py")
spec = importlib.util.spec_from_file_location("upload_latest_garmin", SCRIPT)
uploader = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = uploader
spec.loader.exec_module(uploader)


class UploadMarkerTests(unittest.TestCase):
    def setUp(self):
        self.workouts = [
            (Path(f"2026-10-{day:02d}_120000_Push-Day_{1000 + day}.fit"), str(1000 + day))
            for day in range(1, 5)
        ]

    def test_finds_newer_workouts_after_latest_garmin_marker(self):
        activities = [
            {"description": "[Liftosaur ID 1002]"},
            {"activityName": "Lunch Run", "description": "Easy miles"},
            {"description": "[Liftosaur ID 1001]"},
        ]

        pending, first_run = uploader.pending_workouts(self.workouts, activities)

        self.assertFalse(first_run)
        self.assertEqual(["1003", "1004"], [workout_id for _, workout_id in pending])

    def test_limits_catch_up_batches_to_five_oldest_first(self):
        workouts = self.workouts + [
            (Path(f"2026-10-{day:02d}_120000_Push-Day_{1000 + day}.fit"), str(1000 + day))
            for day in range(5, 9)
        ]

        pending, first_run = uploader.pending_workouts(
            workouts, [{"description": "[Liftosaur ID 1001]"}]
        )

        self.assertFalse(first_run)
        self.assertEqual(["1002", "1003", "1004", "1005", "1006"], [i for _, i in pending])

    def test_requires_explicit_initialization_without_a_marker(self):
        pending, first_run = uploader.pending_workouts(
            self.workouts, [{"activityName": "Morning Run"}]
        )

        self.assertTrue(first_run)
        self.assertEqual(["1004"], [workout_id for _, workout_id in pending])

    def test_rejects_marker_outside_downloaded_history(self):
        with self.assertRaisesRegex(ValueError, "outside the downloaded Liftosaur history"):
            uploader.pending_workouts(
                self.workouts, [{"description": "[Liftosaur ID 9999]"}]
            )

    def test_extracts_activity_id_from_import_response(self):
        response = {
            "detailedImportResult": {
                "successes": [{"internalId": 987654321}],
                "failures": [],
            }
        }

        self.assertEqual("987654321", uploader.find_activity_id(response))

    def test_builds_description_marker_without_changing_title(self):
        marker = uploader.activity_marker("1001")

        self.assertEqual("[Liftosaur ID 1001]", marker)


if __name__ == "__main__":
    unittest.main()
