"""Upload up to five recent Liftosaur workouts that have not been uploaded."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from garminconnect import Garmin


LAST_UPLOADED_VARIABLE = "LAST_GARMIN_UPLOAD_LIFTOSAUR_ID"
MAX_WORKOUTS_PER_RUN = 5


def github_variable_request(method: str, url: str, token: str, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else None
    except HTTPError as error:
        if error.code == 404 and method == "GET":
            return 404, None
        raise


def get_last_uploaded_id(token: str, repository: str) -> str | None:
    url = (
        f"https://api.github.com/repos/{repository}/actions/variables/"
        f"{LAST_UPLOADED_VARIABLE}"
    )
    status, response = github_variable_request("GET", url, token)
    return response["value"] if status == 200 else None


def save_last_uploaded_id(token: str, repository: str, workout_id: str) -> None:
    base_url = f"https://api.github.com/repos/{repository}/actions/variables"
    url = f"{base_url}/{LAST_UPLOADED_VARIABLE}"
    body = {"name": LAST_UPLOADED_VARIABLE, "value": workout_id}
    status, _ = github_variable_request("GET", url, token)
    method = "PATCH" if status == 200 else "POST"
    github_variable_request(method, url if method == "PATCH" else base_url, token, body)


def main() -> int:
    email = os.environ.get("GARMIN_EMAIL", "").strip()
    password = os.environ.get("GARMIN_PASSWORD", "")
    if not email or not password:
        print("GARMIN_EMAIL and GARMIN_PASSWORD must be configured as Actions secrets.", file=sys.stderr)
        return 2

    fit_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "./fit")
    files = sorted(fit_dir.glob("*.fit"))
    if not files:
        print(f"Expected workout FIT files in {fit_dir}, found none.", file=sys.stderr)
        return 2

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repository:
        print("GITHUB_TOKEN and GITHUB_REPOSITORY are required for duplicate protection.", file=sys.stderr)
        return 2

    workouts = []
    for path in files:
        workout_id = path.stem.rsplit("_", 1)[-1]
        if not workout_id.isdigit():
            print(f"Could not read the Liftosaur workout ID from {path.name}.", file=sys.stderr)
            return 2
        workouts.append((path, workout_id))

    try:
        last_uploaded_id = get_last_uploaded_id(token, repository)
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError) as error:
        status = getattr(error, "code", "network error")
        print(
            "Could not check the saved Garmin upload ID; refusing to upload to avoid a duplicate. "
            f"(HTTP {status})",
            file=sys.stderr,
        )
        return 1

    if last_uploaded_id is None:
        # There is no saved baseline yet. Preserve the old first-run behavior and
        # initialize the marker with the newest workout only.
        pending = workouts[-1:]
    else:
        last_index = next(
            (index for index, (_, workout_id) in enumerate(workouts) if workout_id == last_uploaded_id),
            None,
        )
        if last_index is None:
            print(
                "The saved upload ID is outside the downloaded workout history. "
                "Refusing to upload because the correct next workout cannot be identified.",
                file=sys.stderr,
            )
            return 1
        else:
            # FIT files are sorted oldest first, so take the next batch after the
            # saved ID. Further manual runs continue catching up in order.
            pending = workouts[last_index + 1 : last_index + 1 + MAX_WORKOUTS_PER_RUN]
    if not pending:
        print(f"Workout {last_uploaded_id} is already the latest uploaded workout; skipping.")
        return 0

    # Keep third-party request logs from exposing account or session details.
    logging.getLogger("garminconnect").setLevel(logging.CRITICAL)
    try:
        client = Garmin(email=email, password=password)
        client.login()
    except Exception as error:  # Garmin's unofficial endpoints can change without notice.
        print(
            "Garmin upload failed. Check the workflow log for the error type; "
            "also confirm that Garmin sign-in does not require an interactive MFA code. "
            f"({type(error).__name__})",
            file=sys.stderr,
        )
        return 1

    for path, workout_id in pending:
        try:
            client.import_activity(str(path))
        except Exception as error:  # Garmin's unofficial endpoints can change without notice.
            print(
                f"Garmin upload failed for {path.name}. Check the workflow log for the error type; "
                "also confirm that Garmin sign-in does not require an interactive MFA code. "
                f"({type(error).__name__})",
                file=sys.stderr,
            )
            return 1

        try:
            save_last_uploaded_id(token, repository, workout_id)
        except (HTTPError, URLError, TimeoutError, KeyError, ValueError) as error:
            status = getattr(error, "code", "network error")
            print(
                f"Garmin accepted {path.name}, but GitHub could not save its duplicate-protection ID. "
                "Check Garmin Connect before rerunning this workflow. "
                f"(HTTP {status})",
                file=sys.stderr,
            )
            return 1

        print(f"Uploaded workout to Garmin Connect: {path.name}")

    print(f"Uploaded {len(pending)} workout(s); this run is limited to {MAX_WORKOUTS_PER_RUN}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
