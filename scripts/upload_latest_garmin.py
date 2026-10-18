"""Upload recent Liftosaur workouts not already marked in Garmin Connect."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

from garminconnect import Garmin


MAX_WORKOUTS_PER_RUN = 5
ACTIVITY_PAGE_SIZE = 100
MAX_ACTIVITY_PAGES = 10
LIFTOSAUR_MARKER = re.compile(r"\[Liftosaur ID (\d+)\]", re.IGNORECASE)


def marker_ids(activities: list[dict]) -> list[str]:
    ids = []
    for activity in activities:
        description = activity.get("description", "")
        if isinstance(description, str):
            ids.extend(LIFTOSAUR_MARKER.findall(description))
    return ids


def pending_workouts(
    workouts: list[tuple[Path, str]], activities: list[dict]
) -> tuple[list[tuple[Path, str]], bool]:
    uploaded_ids = marker_ids(activities)
    if not uploaded_ids:
        return workouts[-1:], True

    id_to_index = {workout_id: index for index, (_, workout_id) in enumerate(workouts)}
    latest_id = uploaded_ids[0]
    if latest_id not in id_to_index:
        raise ValueError(
            f"Garmin's latest Liftosaur marker ({latest_id}) is outside the downloaded "
            "Liftosaur history; refusing to guess which workouts are new."
        )

    next_index = id_to_index[latest_id] + 1
    return workouts[next_index : next_index + MAX_WORKOUTS_PER_RUN], False


def find_activity_id(upload_response: dict) -> str | None:
    result = upload_response.get("detailedImportResult", upload_response)
    if isinstance(result, dict) and isinstance(result.get("data"), dict):
        result = result["data"].get("detailedImportResult", result["data"])
    if not isinstance(result, dict):
        raise ValueError("Garmin returned an unrecognized upload response.")
    successes = result.get("successes", [])
    if not successes or not isinstance(successes[0], dict):
        failures = result.get("failures", [])
        raise ValueError(f"Garmin rejected the workout import: {failures!r}")
    activity_id = successes[0].get("internalId")
    return str(activity_id) if activity_id is not None else None


def activity_marker(workout_id: str) -> str:
    return f"[Liftosaur ID {workout_id}]"


def main() -> int:
    email = os.environ.get("GARMIN_EMAIL", "").strip()
    password = os.environ.get("GARMIN_PASSWORD", "")
    if not email or not password:
        print("GARMIN_EMAIL and GARMIN_PASSWORD must be configured as Actions secrets.", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser()
    parser.add_argument("fit_dir", nargs="?", default="./fit")
    parser.add_argument("--initialize-from-latest", action="store_true")
    args = parser.parse_args()

    fit_dir = Path(args.fit_dir)
    files = sorted(fit_dir.glob("*.fit"))
    workouts = [
        (path, path.stem.rsplit("_", 1)[-1])
        for path in files
        if path.stem.rsplit("_", 1)[-1].isdigit()
    ]
    if not workouts:
        print(
            f"Expected generated Liftosaur FIT files with numeric IDs in {fit_dir}, found none.",
            file=sys.stderr,
        )
        return 2

    # Keep third-party request logs from exposing account or session details.
    logging.getLogger("garminconnect").setLevel(logging.CRITICAL)
    try:
        client = Garmin(email=email, password=password)
        client.login()
        activities = []
        for page in range(MAX_ACTIVITY_PAGES):
            page_activities = client.get_activities(
                start=page * ACTIVITY_PAGE_SIZE,
                limit=ACTIVITY_PAGE_SIZE,
            )
            if not page_activities:
                break
            activities.extend(page_activities)
            if marker_ids(page_activities):
                break

        pending, first_run = pending_workouts(workouts, activities)
        if first_run and not args.initialize_from_latest:
            print(
                "No Garmin activity with a Liftosaur ID marker was found. "
                "Verify previous imports or rerun with --initialize-from-latest "
                "to upload only the newest Liftosaur workout.",
                file=sys.stderr,
            )
            return 1
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception as error:  # Garmin's unofficial endpoints can change without notice.
        print(
            "Could not identify the latest Liftosaur workout in Garmin Connect. "
            f"({type(error).__name__})",
            file=sys.stderr,
        )
        return 1

    if not pending:
        print("Garmin Connect already contains the latest Liftosaur workout; skipping.")
        return 0

    for path, workout_id in pending:
        try:
            upload_response = client.import_activity(str(path))
        except Exception as error:  # Garmin's unofficial endpoints can change without notice.
            print(
                f"Garmin upload failed for {path.name}. Check the workflow log for the error type; "
                "also confirm that Garmin sign-in does not require an interactive MFA code. "
                f"({type(error).__name__})",
                file=sys.stderr,
            )
            return 1

        try:
            activity_id = find_activity_id(upload_response)
            if not activity_id:
                raise ValueError("Garmin returned no activity ID to mark.")
            client.set_activity_description(activity_id, activity_marker(workout_id))
        except Exception as error:  # Garmin accepted the file, but may not have applied the marker.
            print(
                f"Garmin accepted {path.name}, but the Liftosaur marker could not be set. "
                "Verify the activity in Garmin Connect before rerunning to avoid a duplicate. "
                f"({type(error).__name__})",
                file=sys.stderr,
            )
            return 1

        print(f"Uploaded workout to Garmin Connect: {path.name}")

    print(
        f"Uploaded {len(pending)} workout(s); this run is limited to "
        f"{MAX_WORKOUTS_PER_RUN}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
