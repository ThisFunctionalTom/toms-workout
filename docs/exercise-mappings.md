# Garmin exercise mappings

Edit [shared/exercise-mappings.json](../shared/exercise-mappings.json).
The .NET adapter in `garminFit.fsx` reads this JSON and resolves symbols in the
Garmin FIT SDK. There are no separate mapping tables to synchronize.

See the [full catalog coverage report](exercise-catalog-audit.md) for every
built-in exercise, its mapping, and any limitation. The catalog snapshot was
retrieved through Liftosaur MCP on 2026-09-24. Additional historical aliases and
custom imported names are retained separately in the same shared mapping file.

## Matching and mapping decisions

Names match exactly after trimming and lowercasing. Equipment suffixes are
significant. A name with an unspecified equipment suffix uses Liftosaur's default,
checked against its [exercise definitions](https://github.com/astashov/liftosaur/blob/master/src/models/exercise.ts).
For example, Bicep Curl uses dumbbells, Face Pull uses a band, Skullcrusher uses
an EZ bar, and Snatch uses a dumbbell.

Each entry contains an array of names, Garmin category/subtype symbol names, a
quality field, and a note:

- `exact`: a corresponding movement/equipment subtype.
- `generic`: a broader movement subtype, with the lost detail explained.
- `category`: a relevant category but no suitable subtype; subtype is null.
- `unsupported`: no suitable mapping; category and subtype are both null.

Do not strip equipment suffixes or match unfamiliar names by similarity. A machine
press should not silently turn into a dumbbell or barbell press. Do not substitute
a different movement to hide an Unknown label. For example, FIT's crunch
`legExtensions` is not the machine knee-extension exercise; the banded extension
code is used only for the explicitly banded variant.

Assisted pull-ups, chin-ups, and dips use the base movement as a documented
generic match. Assisted exercises export **0 kg added weight**, with assistance
in kg listed in workout step notes in set order (including marked warmups).
Garmin may not display these notes in every activity view. The shared logic in
`shared/WorkoutConversion.fs` recognizes names containing the word `Assisted`,
machine-assisted chin-ups, pull-ups, triceps dips and pistol squats, and band-assisted
pull-ups/chin-ups. Other machine and band exercises retain their resistance weights.
FIT's standard set weight is unsigned, so negative assistance cannot be stored there.

Garmin may still show category-only and unsupported entries as Unknown.
Original exercise names remain in workout step names and notes. FIT profile
support does not guarantee identical exercise labels in every Garmin client.

## Updating and validating

1. Update the shared JSON. Use symbols present in the installed Garmin FIT SDK,
   not guessed numeric codes. Explain all generic or incomplete matches.
2. Refresh `tests/liftosaur-exercises.json` from Liftosaur MCP when its catalog
   changes. This is an independent coverage snapshot, not a generated copy of
   the mapping table.
3. Run `node scripts/generate-mapping-audit.mjs` to regenerate the coverage report.
4. Run `dotnet fsi conversion.tests.fsx` for workout conversion regressions and
   `dotnet fsi tests/generate-reference.fsx` to encode sample FIT files and all
   mapped exercises through the .NET Garmin FIT SDK.

The .NET CLI requires the shared JSON alongside the repository scripts.

Reconvert workouts to include new mappings. Activities already imported into
Garmin are not changed automatically.
