"""Interactive comparison of an Apple Health export and a synthetic twin.

Run from the workspace root: ``cd persona_gen && uv run --extra notebook marimo edit notebooks/twin_explorer.py``.
Enter the archive and dataset paths, then pick patient, source and date range. Start with a short range: the
export is streamed on each load. Changing the day or context afterwards does not rescan; load a wider range
first if you need one. Real workouts include all writers, other real records use the chosen device family, and
synthetic records use the selected source. Missing readings are not zero or necessarily non-wear. Daily and weekly
step summaries apportion interval counts across bins, so incomplete coverage and overlapping sources affect
totals. Distributions weight records equally, so different sampling rates can bias them. A twin is a stochastic
simulation, so use the views for exploratory comparison only. The views show records from the input export, and
saved figures can contain personal measurements.
"""

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    import sys
    from datetime import date, timedelta
    from pathlib import Path

    import marimo as mo

    package_dir = (mo.notebook_dir() or Path(__file__).parent).parent
    project_dir = package_dir.parent  # workspace root: relative data paths such as .local/... resolve here
    if str(package_dir / "src") not in sys.path:
        sys.path.insert(0, str(package_dir / "src"))

    from persona_gen.validation.explorer import (
        METRIC_INFO,
        comparison_table,
        day_chart,
        distribution_chart,
        health_chart,
        metadata,
        real_records,
        single_workout_chart,
        slice_window,
        steps_chart,
        synthetic_records,
        week_chart,
        workout_options,
    )

    return (
        date,
        comparison_table,
        day_chart,
        distribution_chart,
        health_chart,
        METRIC_INFO,
        metadata,
        mo,
        project_dir,
        real_records,
        single_workout_chart,
        slice_window,
        steps_chart,
        synthetic_records,
        timedelta,
        week_chart,
        workout_options,
    )


@app.cell
def _(mo):
    mo.md("""
    # Real export / synthetic twin explorer

    Pick an export, wearable family, dataset and matching twin/source. Relative paths
    resolve from the workspace root. Loading scans the export once for the selected
    comparison. Chart controls use those loaded records.

    The twin is a new simulation, not a replay. Compare contexts and ranges, not identical
    timestamps. Blank cells mean no observations, not zero or necessarily non-wear. Real
    workouts include all sources; sleep uses the selected device family. Times are local.
    """)
    return


@app.cell
def _(mo):
    setup = mo.ui.dictionary(
        {
            "archive": mo.ui.text(label="Apple Health archive path"),
            "family": mo.ui.dropdown(
                options=["apple_watch", "garmin", "iphone"], value="apple_watch", label="Real device family"
            ),
            "dataset": mo.ui.text(value=".local/plots/twins-dataset", label="Synthetic dataset directory"),
        }
    ).form(submit_button_label="Inspect dataset")
    setup  # noqa: B018
    return (setup,)


@app.cell
def _(metadata, mo, project_dir, setup):
    mo.stop(setup.value is None, mo.md("Enter the archive and dataset paths to compare records."))
    config = setup.value
    people, devices, recipe = metadata(project_dir / config["dataset"])
    mo.vstack(
        [
            mo.md(f"**Dataset recipe:** {recipe}"),
            mo.md("**Personas and anchors**"),
            mo.ui.table(people),
            mo.md("**Device sources**"),
            mo.ui.table(devices),
        ]
    )
    return config, devices, people, recipe


@app.cell
def _(config, date, devices, mo, people, recipe, timedelta):
    people_options = people.patient_id.astype(str).tolist()
    source_options = sorted(devices.source_name.dropna().astype(str).unique().tolist())
    mo.stop(not people_options or not source_options, mo.md("This dataset has no personas or device sources."))
    preferred = {"apple_watch": "Apple Watch", "garmin": "Connect", "iphone": "iPhone"}.get(config["family"])
    matching_devices = devices[devices.source_name == preferred]
    default_patient = str(matching_devices.iloc[0].patient_id) if not matching_devices.empty else people_options[0]
    patient_sources = devices[devices.patient_id == default_patient].source_name.dropna().astype(str).tolist()
    default_source = (
        preferred if preferred in patient_sources else (patient_sources[0] if patient_sources else source_options[0])
    )
    first_day = date.fromisoformat(recipe["start"])
    last_day = first_day + timedelta(days=min(6, recipe["days"] - 1))
    settings = mo.ui.dictionary(
        {
            "patient": mo.ui.dropdown(options=people_options, value=default_patient, label="Synthetic patient"),
            "source": mo.ui.dropdown(
                options=source_options, value=default_source, label="Synthetic source (see table above)"
            ),
            "start": mo.ui.date(value=recipe["start"], label="First local day"),
            "end": mo.ui.date(value=last_day, label="Last local day (inclusive)"),
        }
    ).form(submit_button_label="Load comparison")
    defaults = {"patient": default_patient, "source": default_source, "start": first_day, "end": last_day}
    settings  # noqa: B018
    return defaults, settings


@app.cell
def _(config, defaults, mo, project_dir, real_records, settings, synthetic_records):
    s = settings.value or defaults
    mo.stop(s["end"] < s["start"], mo.md("The last day must be on or after the first day."))
    mo.stop(not config["archive"].strip(), mo.md("Enter the path to an Apple Health archive above."))
    real = real_records(project_dir / config["archive"], config["family"], s["start"], s["end"])
    twin, truth = synthetic_records(project_dir / config["dataset"], s["patient"], s["source"], s["start"], s["end"])
    mo.md(
        f"Loaded **{len(real):,} real records**, **{len(twin):,} synthetic records**, and "
        f"**{len(truth):,} synthetic truth intervals**."
    )
    return real, s, truth, twin


@app.cell
def _(mo, s):
    day = mo.ui.date(value=s["start"], start=s["start"], stop=s["end"], label="First day / day to inspect")
    duration = mo.ui.dropdown(
        options={"1 day": 1, "7 days": 7, "14 days": 14, "30 days": 30, "Through loaded end": 0},
        value="7 days",
        label="Display window",
    )
    context = mo.ui.dropdown(
        options={"All records": "all", "Asleep": "sleep", "Workout": "workout", "Other / unknown": "other / unknown"},
        value="All records",
        label="Heart-rate context (day and distributions)",
    )
    step_period = mo.ui.dropdown(options={"Daily": "daily", "Weekly": "weekly"}, value="Daily", label="Step totals")
    mo.vstack(
        [
            mo.md("## Display controls\nChoose a starting day and window within the loaded dates."),
            mo.hstack([day, duration, context, step_period], justify="start"),
        ]
    )
    return context, day, duration, step_period


@app.cell
def _(day, duration, real, s, slice_window, timedelta, twin):
    view_start = day.value
    view_end = min(s["end"], view_start + timedelta(days=duration.value - 1)) if duration.value else s["end"]
    real_view = slice_window(real, view_start, view_end)
    twin_view = slice_window(twin, view_start, view_end)
    return real_view, twin_view, view_end, view_start


@app.cell
def _(METRIC_INFO, mo):
    selected_metric = mo.ui.dropdown(
        options={info[0]: name for name, info in METRIC_INFO.items()}, value="Steps", label="Metric"
    )
    mo.vstack(
        [
            mo.md(
                "## Health metric comparison\n"
                "A single day shows hourly totals for steps and energy, or individual readings for other metrics. "
                "Longer windows show daily totals or medians and observed ranges. Missing periods are blank."
            ),
            selected_metric,
        ]
    )
    return (selected_metric,)


@app.cell
def _(health_chart, mo, real_view, selected_metric, twin_view, view_end, view_start):
    _fig, _counts = health_chart(real_view, twin_view, selected_metric.value, view_start, view_end)
    mo.vstack(
        [
            mo.md(
                f"Real: {_counts['Real']:,} records · Twin: {_counts['Twin']:,} records."
                " Totals include overlapping records."
            ),
            mo.ui.plotly(_fig),
        ]
    )
    return


@app.cell
def _(comparison_table, mo, real_view, selected_metric, twin_view):
    _metric = selected_metric.value
    _sections = [
        mo.md("### Record differences"),
        mo.ui.table(comparison_table(real_view, twin_view, _metric)),
        mo.md("First 1,000 records per source in the display window."),
    ]
    for _name, _frame in (("Real records", real_view), ("Synthetic records", twin_view)):
        _records = _frame[_frame.metric == _metric].sort_values("start")
        _sections.extend([mo.md(f"**{_name}**"), mo.ui.table(_records.head(1000))])
    mo.vstack(_sections)
    return


@app.cell
def _(context, day, day_chart, mo, real_view, truth, twin_view):
    mo.vstack(
        [
            mo.md(
                "## Individual day\n"
                "Use the context selector to filter heart rate. Gray lines show the synthetic truth target. "
                "Steps are interval rates."
            ),
            mo.ui.plotly(day_chart(real_view, twin_view, truth, day.value, context.value)),
        ]
    )
    return


@app.cell
def _(day, mo, real_view, step_period, steps_chart, twin_view, view_end, view_start):
    _fig, _totals = steps_chart(real_view, twin_view, view_start, view_end, day.value, step_period.value)
    _description = " · ".join(
        f"{name}: {n}/{days} days with step records; observed total {total:,.0f}"
        if total is not None
        else f"{name}: no step records"
        for name, (n, days, total) in _totals.items()
    )
    mo.vstack(
        [
            mo.md(
                f"## Steps · {view_start} to {view_end}\n{_description}\n\n"
                "Intervals crossing bins are apportioned at a constant rate. Totals include overlapping records. "
                "Weeks run Monday through Sunday and may be partial at the edges."
            ),
            mo.ui.plotly(_fig),
        ]
    )
    return


@app.cell
def _(mo, real_view, twin_view, view_end, view_start, week_chart):
    mo.vstack(
        [
            mo.md(
                "## Time-of-day overview\n"
                "Each cell shows the median reading in that local hour. Blank cells mark missing data."
            ),
            mo.ui.plotly(week_chart(real_view, twin_view, view_start, view_end)),
        ]
    )
    return


@app.cell
def _(context, distribution_chart, mo, real_view, twin_view, view_end, view_start):
    fig, distance, counts = distribution_chart(real_view, twin_view, context.value)
    summary = (
        f"Wasserstein distance: **{distance:.1f} bpm**"
        if distance is not None
        else "Distance unavailable: one or both selections have no readings."
    )
    mo.vstack(
        [
            mo.md(
                f"## Heart-rate values · {view_start} to {view_end}\n"
                f"{summary} · real n={counts[0]:,}, twin n={counts[1]:,}."
                " Each record has equal weight. Context comes from recorded sleep and workout intervals."
            ),
            mo.ui.plotly(fig),
        ]
    )
    return


@app.cell
def _(mo, real_view, twin_view, workout_options):
    real_workouts, real_choices = workout_options(real_view)
    twin_workouts, twin_choices = workout_options(twin_view)
    real_workout = mo.ui.dropdown(
        options={"No workout": None, **real_choices}, value=next(iter(real_choices), "No workout"), label="Real workout"
    )
    twin_workout = mo.ui.dropdown(
        options={"No workout": None, **twin_choices}, value=next(iter(twin_choices), "No workout"), label="Twin workout"
    )
    mo.vstack(
        [
            mo.md("## Compare individual workouts\nCurves align at workout start. Colored dotted lines mark the ends."),
            mo.hstack([real_workout, twin_workout], justify="start"),
        ]
    )
    return real_workout, real_workouts, twin_workout, twin_workouts


@app.cell
def _(mo, real, real_workout, real_workouts, single_workout_chart, twin, twin_workout, twin_workouts):
    _fig, _info = single_workout_chart(real, twin, real_workouts, twin_workouts, real_workout.value, twin_workout.value)
    mo.vstack([mo.md(" · ".join(_info) + ". Heart-rate lines break at gaps over five minutes."), mo.ui.plotly(_fig)])
    return


if __name__ == "__main__":
    app.run()
