"""Upload the FIT file generated for the latest Liftosaur workout."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from garminconnect import Garmin


def main() -> int:
    email = os.environ.get("GARMIN_EMAIL", "").strip()
    password = os.environ.get("GARMIN_PASSWORD", "")
    if not email or not password:
        print("GARMIN_EMAIL and GARMIN_PASSWORD must be configured as Actions secrets.", file=sys.stderr)
        return 2

    fit_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "./fit")
    files = sorted(fit_dir.glob("*.fit"))
    if len(files) != 1:
        print(f"Expected exactly one workout FIT file in {fit_dir}, found {len(files)}.", file=sys.stderr)
        return 2

    # Keep third-party request logs from exposing account or session details.
    logging.getLogger("garminconnect").setLevel(logging.CRITICAL)
    try:
        client = Garmin(email=email, password=password)
        client.login()
        client.import_activity(str(files[0]))
    except Exception as error:  # Garmin's unofficial endpoints can change without notice.
        print(
            "Garmin upload failed. Check the workflow log for the error type; "
            "also confirm that Garmin sign-in does not require an interactive MFA code. "
            f"({type(error).__name__})",
            file=sys.stderr,
        )
        return 1

    print(f"Uploaded latest workout to Garmin Connect: {files[0].name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
