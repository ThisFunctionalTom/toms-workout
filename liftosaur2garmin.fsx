#load "garminFit.fsx"

open System
open System.IO
open System.Text.Json
open GarminFit
open Liftosaur
open WorkoutConversion

// ----------------------------------------------------------------------
// CLI
// ----------------------------------------------------------------------

let args = fsi.CommandLineArgs |> Array.skip 1

if args.Length < 1 then
    failwith "Usage: dotnet fsi liftosaur2garmin.fsx -- --full-export <n> [output-dir] | --incremental <garmin-activities.json> [output-dir]"

let mode = args[0]
let outputDir =
    match mode, args.Length with
    | "--full-export", n when n >= 3 -> args[2]
    | "--incremental", n when n >= 3 -> args[2]
    | "--full-export", _
    | "--incremental", _ -> "./fit"
    | _ -> failwith "Choose --full-export or --incremental."

let apiKey =
    Environment.GetEnvironmentVariable("LIFTOSAUR_API_KEY")
    |> Option.ofObj
    |> Option.defaultWith (fun () -> failwith "Set LIFTOSAUR_API_KEY=lftsk_... first")

Directory.CreateDirectory(outputDir) |> ignore

// ----------------------------------------------------------------------
// Conversion helpers
// ----------------------------------------------------------------------

let workoutPath outputDir recordId (workout: Workout) =
    let day =
        if String.IsNullOrWhiteSpace(workout.DayName) then "strength"
        else safeName workout.DayName
    let date = workout.Start.ToString("yyyy-MM-dd_HHmmss")
    Path.Combine(outputDir, $"{date}_{day}_{recordId}.fit")

let countTimelineEntries predicate timeline =
    timeline |> List.sumBy (fun entry -> if predicate entry then 1 else 0)

let writeWorkout outputDir record =
    let workout = parseWorkout record.Text
    let path = workoutPath outputDir record.Id workout
    let timeline = buildTimeline workout
    let activeCount = countTimelineEntries (function ActiveSet _ -> true | _ -> false) timeline
    let restCount = countTimelineEntries (function Rest _ -> true | _ -> false) timeline
    writeFitFile workout path
    printfn "Wrote %s (%d active sets, %d rests, %ds session)" path activeCount restCount workout.DurationSeconds

let writeManifest records =
    records
    |> List.map (fun record ->
        let workout = parseWorkout record.Text
        {| id = string record.Id
           path = Path.GetFullPath(workoutPath outputDir record.Id workout)
           name = workoutName workout
           start = workout.Start.ToUniversalTime().ToString("O") |})
    |> fun entries ->
        File.WriteAllText(Path.Combine(outputDir, "fit-manifest.json"), JsonSerializer.Serialize(entries))

let runFullExport n =
    let records =
        use http = createClient apiKey
        downloadWorkouts http n None []
        |> Async.RunSynchronously
        |> List.sortBy (fun record -> (parseWorkout record.Text).Start)
    printfn "Downloaded %d Liftosaur workout(s)." records.Length
    records |> List.iter (writeWorkout outputDir)
    writeManifest records

let runIncremental activitiesPath =
    use activitiesDocument = JsonDocument.Parse(File.ReadAllText(activitiesPath))
    let activities = activitiesDocument.RootElement.EnumerateArray() |> Seq.toList
    let activityKeys =
        activities
        |> List.choose (fun activity ->
            let name =
                match activity.TryGetProperty("activityName") with
                | true, value when value.ValueKind = JsonValueKind.String -> value.GetString().Trim()
                | _ -> ""
            let timestamp =
                match activity.TryGetProperty("startTimeGMT") with
                | true, value when value.ValueKind = JsonValueKind.String ->
                    match DateTimeOffset.TryParse(
                        value.GetString(),
                        Globalization.CultureInfo.InvariantCulture,
                        Globalization.DateTimeStyles.AssumeUniversal
                    ) with
                    | true, parsed -> Some parsed
                    | _ -> None
                | _ -> None
            if String.IsNullOrWhiteSpace(name) then None
            else timestamp |> Option.map (fun start -> name, start))

    let matchingActivityCount (record: LiftosaurRecord) =
        let workout = parseWorkout record.Text
        activityKeys
        |> List.sumBy (fun (name, start) ->
            if String.Equals(name, workoutName workout, StringComparison.OrdinalIgnoreCase)
               && abs((start.ToUniversalTime() - workout.Start.ToUniversalTime()).TotalSeconds) <= 60.0 then 1
            else 0)

    let isBoundary record =
        match matchingActivityCount record with
        | 0 -> false
        | 1 -> true
        | count ->
            let workout = parseWorkout record.Text
            failwithf "Found %d Garmin activities matching '%s' at %O within 60 seconds. Resolve the ambiguity before retrying."
                count (workoutName workout) workout.Start

    let records, foundBoundary, hasMore =
        use http = createClient apiKey
        downloadWorkoutsUntil http 50 1000 isBoundary |> Async.RunSynchronously

    if not foundBoundary then
        if hasMore then
            failwith "No unique Garmin name/time match found in the latest 1,000 Liftosaur workouts. Use --full-export for a full export or investigate the Garmin baseline."
        else
            failwith "No unique Garmin name/time match found before Liftosaur history ended. Refusing to treat this as a first run."

    let newRecords = records |> List.rev |> List.tail
    printfn "Found prior Garmin workout after scanning %d Liftosaur records; exporting %d newer workout(s)." records.Length newRecords.Length
    newRecords |> List.iter (writeWorkout outputDir)
    writeManifest newRecords

match mode with
| "--full-export" ->
    if args.Length < 2 then failwith "--full-export requires a workout count."
    runFullExport (int args[1])
| "--incremental" ->
    if args.Length < 2 then failwith "--incremental requires a Garmin activities JSON file."
    runIncremental args[1]
| _ -> failwith "Choose --full-export or --incremental."
