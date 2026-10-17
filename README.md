# Liftosaur workout tools

This repository contains a Liftosaur-to-Garmin FIT converter, a public workout
progress page, and one GitHub Actions workflow that refreshes the page and uploads
up to five recent workouts to Garmin Connect when run manually.

## Convert workouts locally

Requires .NET SDK 10. The CLI downloads the newest Liftosaur workouts and writes
Garmin FIT activity files to the selected output directory:

```powershell
$env:LIFTOSAUR_API_KEY = 'your-key'
dotnet fsi liftosaur2garmin.fsx -- 10 ./fit
```

The personal Connect IQ watch app lives in the separate `liftosaur-garmin`
repository. With sibling local checkouts, see its README for scope and build
instructions.

## Progress page

The GitHub Pages site displays a continuous training calendar and strength trends
for squat, bench press, deadlift, and overhead press. Calendar cells show working
sets and reps with shading based on weighted volume. Strength charts show each
workout's heaviest working set and Epley estimated 1RM. Raw Liftosaur workout text
and API credentials are not published.

Generate fresh summary data locally and preview the static page with Python:

```powershell
$env:LIFTOSAUR_API_KEY = 'your-key'
dotnet fsi progress/generate.fsx
python -m http.server 8000 --directory progress/site
```

Open `http://localhost:8000`. The generator writes `progress/site/data.json` using
summary fields only. Clear the API key from the current PowerShell session when
finished:

```powershell
Remove-Item Env:LIFTOSAUR_API_KEY
```

## Refresh and upload from GitHub Actions

There is one workflow: **Refresh progress and upload Garmin workout**. Its manual
`workflow_dispatch` run refreshes the progress data from Liftosaur, generates a
FIT history, uploads pending workouts to Garmin Connect, and deploys the progress
page. Pushes to `main` refresh and deploy the progress page without uploading
workouts. The uploader checks the latest 200 workouts, skips workouts
through the last saved upload ID, and uploads pending workouts oldest first, with
a maximum of five per run. If more than five are pending, run the workflow again
to continue the catch-up.

After adding the secrets below, open the [workflow page](https://github.com/ThisFunctionalTom/toms-workout/actions/workflows/pages.yml), select the `main` branch, and tap **Run workflow** after a workout.

Add these as repository Actions secrets under **Settings → Secrets and variables
→ Actions**:

- `LIFTOSAUR_API_KEY`
- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`

The Garmin uploader uses the unofficial `garminconnect` client because Garmin's
public APIs do not provide this completed-activity upload operation. Garmin can
change its private endpoints without notice. The upload also needs non-interactive
Garmin sign-in; if the account requires an MFA code on each login, the workflow
will fail.

To publish from Actions, enable GitHub Pages with **Settings → Pages → Build and
deployment → GitHub Actions**, then set the repository variable `PAGES_ENABLED` to
`true`. The site is published at
[https://thisfunctionaltom.github.io/toms-workout/](https://thisfunctionaltom.github.io/toms-workout/).

## Project files

- `shared/WorkoutCore.fs`: workout types and Liftosaur workout-text parsing.
- `shared/WorkoutConversion.fs`: workout timeline reconstruction and names.
- `shared/exercise-mappings.json`: exercise-to-Garmin FIT metadata.
- `liftosaur.fsx`: Liftosaur API client.
- `garminFit.fsx`: Garmin .NET FIT encoding.
- `liftosaur2garmin.fsx`: local history downloader and FIT converter.
- `progress/generate.fsx`: public progress summary generator.
- `progress/site/`: static progress page and generated summary.
- `scripts/upload_latest_garmin.py`: GitHub Actions Garmin Connect upload helper.

## Checks

The credential-free F# checks use synthetic workout data and mocked API responses:

```powershell
dotnet fsi conversion.tests.fsx
dotnet fsi liftosaur.tests.fsx
dotnet fsi syncPrograms.tests.fsx
```

Source control in this workspace uses Jujutsu (`jj`).
