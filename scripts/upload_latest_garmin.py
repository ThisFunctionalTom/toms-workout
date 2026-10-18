"""Incrementally export and upload Liftosaur workouts to Garmin Connect."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from garminconnect import Garmin


ACTIVITY_PAGE_SIZE = 100
MAX_ACTIVITY_PAGES = 10
MATCH_TOLERANCE_SECONDS = 60


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def activity_key(activity: dict) -> tuple[str, datetime] | None:
    name = activity.get("activityName")
    if not isinstance(name, str) or not name.strip():
        return None
    start = parse_timestamp(activity.get("startTimeGMT"))
    return (name.strip(), start) if start else None


def manifest_key(entry: dict) -> tuple[str, datetime] | None:
    name = entry.get("name")
    start = parse_timestamp(entry.get("start"))
    if not isinstance(name, str) or not name.strip() or start is None:
        return None
    return name.strip(), start


def matching_activities(entry: dict, activities: list[dict]) -> list[dict]:
    target = manifest_key(entry)
    if target is None:
        raise ValueError(f"Invalid workout entry in generated manifest: {entry!r}")
    name, start = target
    matches = []
    for activity in activities:
        candidate = activity_key(activity)
        if candidate is None:
            continue
        candidate_name, candidate_start = candidate
        if (
            candidate_name.casefold() == name.casefold()
            and abs((candidate_start - start).total_seconds()) <= MATCH_TOLERANCE_SECONDS
        ):
            matches.append(activity)
    return matches


def require_unique_match(entry: dict, activities: list[dict]) -> dict | None:
    matches = matching_activities(entry, activities)
    if len(matches) > 1:
        raise ValueError(
            f"Multiple Garmin activities match '{entry.get('name')}' at {entry.get('start')}. "
            "Resolve the duplicate activities before retrying."
        )
    return matches[0] if matches else None


def load_garmin_activities(client: Garmin) -> list[dict]:
    activities: list[dict] = []
    for page in range(MAX_ACTIVITY_PAGES):
        page_activities = client.get_activities(start=page * ACTIVITY_PAGE_SIZE, limit=ACTIVITY_PAGE_SIZE)
        if not page_activities:
            break
        activities.extend(page_activities)
    return activities


def run_incremental_export(output_dir: Path, activities: list[dict], api_key: str) -> None:
    with tempfile.TemporaryDirectory(prefix="liftosaur-garmin-") as temp_dir:
        activities_path = Path(temp_dir) / "garmin-activities.json"
        activities_path.write_text(json.dumps(activities), encoding="utf-8")
        command = [
            "dotnet", "fsi", "liftosaur2garmin.fsx", "--", "--incremental",
            str(activities_path), str(output_dir),
        ]
        env = os.environ.copy()
        env["LIFTOSAUR_API_KEY"] = api_key
        result = subprocess.run(command, env=env, check=False)
        if result.returncode != 0:
            raise RuntimeError("Incremental Liftosaur FIT export failed; no Garmin uploads were attempted.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fit_dir", nargs="?", default="./fit")
    parser.add_argument("--max-upload", type=int, default=5)
    args = parser.parse_args()
    if args.max_upload <= 0:
        parser.error("--max-upload must be positive")

    email = os.environ.get("GARMIN_EMAIL", "").strip()
    password = os.environ.get("GARMIN_PASSWORD", "")
    if not email or not password:
        print("GARMIN_EMAIL and GARMIN_PASSWORD must be configured.", file=sys.stderr)
        return 2

    api_key = os.environ.get("LIFTOSAUR_API_KEY", "").strip()
    if not api_key:
        print("LIFTOSAUR_API_KEY is required for incremental mode.", file=sys.stderr)
        return 2

    output_dir = Path(args.fit_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    logging.getLogger("garminconnect").setLevel(logging.CRITICAL)

    try:
        client = Garmin(email=email, password=password)
        client.login()
        activities = load_garmin_activities(client)

        run_incremental_export(output_dir, activities, api_key)

        manifest_path = output_dir / "fit-manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entries = [entry for entry in manifest if isinstance(entry, dict)]
        else:
            entries = [
                {"path": str(path), "name": path.stem, "start": ""}
                for path in sorted(output_dir.glob("*.fit"))
            ]

        pending: list[dict] = []
        for entry in entries:
            existing = require_unique_match(entry, activities) if manifest_path.exists() else None
            if existing is None:
                fit_path = Path(entry["path"])
                if not fit_path.is_absolute():
                    fit_path = output_dir / fit_path
                if fit_path.is_file():
                    pending.append({**entry, "path": str(fit_path)})

        pending.sort(key=lambda entry: parse_timestamp(entry.get("start")) or datetime.min.replace(tzinfo=timezone.utc))
        pending = pending[: args.max_upload]
        if not pending:
            print("Garmin Connect already contains all generated workouts; nothing to upload.")
            return 0

        for entry in pending:
            path = entry["path"]
            try:
                client.import_activity(path)
            except Exception as error:
                print(
                    f"Garmin upload failed for {Path(path).name} ({type(error).__name__}). "
                    "Check Garmin Connect before retrying in case the import succeeded.",
                    file=sys.stderr,
                )
                return 1
            print(f"Uploaded workout to Garmin Connect: {Path(path).name}")

        print(f"Uploaded {len(pending)} workout(s).")
        return 0
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Garmin incremental upload failed ({type(error).__name__}).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
