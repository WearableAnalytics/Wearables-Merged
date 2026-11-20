"""Date-window readers and charts for the twin exploration notebook."""

from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pyarrow.compute as pc
from plotly.subplots import make_subplots
from scipy.stats import wasserstein_distance

from ..dataset import open_dataset
from ..sources.healthkit_xml import HK, HKC, export_files, family, xml_entries

# TODO: Read converted Parquet to avoid scanning the archive on each load.

METRICS = {
    HK + "HeartRate": "heart_rate",
    HK + "StepCount": "steps",
    HK + "RestingHeartRate": "resting_heart_rate",
    HK + "HeartRateVariabilitySDNN": "hrv_sdnn",
    HK + "RespiratoryRate": "respiratory_rate",
    HK + "OxygenSaturation": "oxygen_saturation",
    HK + "ActiveEnergyBurned": "active_energy",
    HKC + "SleepAnalysis": "sleep",
}
METRIC_INFO = {
    "heart_rate": ("Heart rate", "bpm", False),
    "resting_heart_rate": ("Resting heart rate", "bpm", False),
    "hrv_sdnn": ("Heart-rate variability (SDNN)", "ms", False),
    "respiratory_rate": ("Respiratory rate", "breaths/min", False),
    "oxygen_saturation": ("Blood oxygen", "%", False),
    "steps": ("Steps", "steps", True),
    "active_energy": ("Active energy", "kcal", True),
}
COLUMNS = ["metric", "start", "end", "value", "category", "source"]


def _local(value):
    return pd.Timestamp(value).tz_localize(None)


def real_records(archive: Path, device_family: str, start, end):
    """Stream an export; keep only selected family and overlapping local dates.

    Workouts are included regardless of source: third-party workout writers often differ
    from the selected watch source. All returned timestamps are local wall times.
    """
    lo, hi = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    rows = []
    found = False
    for kind, _, stream in export_files(archive):
        if kind != "health-xml":
            continue
        found = True
        for entry in xml_entries(stream):
            tag = entry.tag
            metric = METRICS.get(entry.get("type")) if tag == "Record" else "workout" if tag == "Workout" else None
            if not metric or (
                metric != "workout" and family(entry.get("sourceName", ""), entry.get("device")) != device_family
            ):
                continue
            if not (start_date := entry.get("startDate")):
                continue
            a = _local(datetime.fromisoformat(start_date))
            b = _local(datetime.fromisoformat(entry.get("endDate") or start_date))
            if a >= hi or (b < lo if b == a else b <= lo):
                continue
            value = entry.get("value")
            try:
                value = float(value) if value is not None else None
            except ValueError:
                value = None
            # HealthKit stores percent quantities as fractions even when unit is "%".
            if metric == "oxygen_saturation" and value is not None and entry.get("unit") == "%":
                value *= 100
            category = entry.get("value") if metric == "sleep" else entry.get("workoutActivityType")
            if metric == "sleep":
                category = (category or "").replace("HKCategoryValueSleepAnalysis", "").lower()
            rows.append((metric, a, b, value, category, entry.get("sourceName", "")))
    if not found:
        raise ValueError("No Apple Health XML found in archive")
    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["start"] = pd.to_datetime(frame["start"])
    frame["end"] = pd.to_datetime(frame["end"])
    return frame


def synthetic_records(root: Path, patient: str, source: str, start, end):
    ds = open_dataset(root)
    # UTC bounds include timezone offsets and intervals crossing the selected days.
    lo = datetime.combine(start, time.min, tzinfo=UTC) - timedelta(days=1)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC) + timedelta(days=1)
    base = (pc.field("patient_id") == patient) & (pc.field("start") < hi) & (pc.field("end") >= lo)
    cols = ["metric", "start", "end", "start_offset_min", "end_offset_min", "value", "category", "source_name"]
    obs = ds.table(
        "observations",
        columns=cols,
        filter=base & (pc.field("source_name") == source) & pc.field("metric").isin([*METRIC_INFO, "sleep"]),
    ).to_pandas()

    def localize(df, start_offset, end_offset):
        df["start"] = pd.to_datetime(df["start"], utc=True).dt.tz_localize(None) + pd.to_timedelta(
            df[start_offset], unit="min"
        )
        df["end"] = pd.to_datetime(df["end"], utc=True).dt.tz_localize(None) + pd.to_timedelta(
            df[end_offset], unit="min"
        )
        return df

    obs = localize(obs, "start_offset_min", "end_offset_min").rename(columns={"source_name": "source"})
    workouts = ds.table(
        "workouts",
        columns=["start", "end", "start_offset_min", "activity", "source_name"],
        filter=base & (pc.field("source_name") == source),
    ).to_pandas()
    workouts = localize(workouts, "start_offset_min", "start_offset_min").rename(
        columns={"activity": "category", "source_name": "source"}
    )
    workouts["metric"], workouts["value"] = "workout", np.nan
    records = pd.concat([obs[COLUMNS], workouts[COLUMNS]], ignore_index=True)
    left, right = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    records = records[
        (records.start < right) & ((records.end > left) | ((records.start == records.end) & (records.start >= left)))
    ]
    truth = ds.table(
        "truth_intervals", columns=["start", "end", "offset_min", "state", "hr_target"], filter=base
    ).to_pandas()
    truth = localize(truth, "offset_min", "offset_min")
    return records, truth


def metadata(root):
    ds = open_dataset(Path(root))
    people = ds.table("personas", columns=["patient_id", "anchor", "anchor_kind"]).to_pandas()
    devices = ds.table("devices", columns=["patient_id", "source_name", "model"]).to_pandas().drop_duplicates()
    return people, devices, ds.manifest["recipe"]


def day_chart(real, synthetic, truth, day, context="all"):
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=(
            "Real and twin heart rate with synthetic truth target",
            "Steps per minute (interval records)",
            "Sleep and workouts",
        ),
    )
    lo, hi = pd.Timestamp(day), pd.Timestamp(day) + pd.Timedelta(days=1)
    for frame, name, color in [(real, "Real", "#1976d2"), (synthetic, "Twin", "#e27624")]:
        hr = _contexts(frame)
        hr = hr[(hr.start >= lo) & (hr.start < hi)]
        if context != "all":
            hr = hr[hr.context == context]
        fig.add_trace(
            go.Scattergl(
                x=hr.start,
                y=hr.value,
                mode="markers",
                name=name + " HR",
                marker={"size": 4, "color": color},
                customdata=hr.source,
                hovertemplate="%{x}<br>%{y:.1f} bpm<br>%{customdata}<extra></extra>",
            ),
            row=1,
            col=1,
        )
        steps = frame[(frame.metric == "steps") & (frame.end > lo) & (frame.start < hi)].copy()
        duration = (steps.end - steps.start).dt.total_seconds() / 60
        steps = steps[duration > 0].copy()
        steps["rate"] = steps.value / duration[duration > 0]
        fig.add_trace(
            go.Scattergl(
                x=steps.start,
                y=steps.rate,
                mode="markers",
                name=name + " steps/min",
                marker={"size": 5, "color": color},
            ),
            row=2,
            col=1,
        )
        for metric in ("sleep", "workout"):
            intervals = frame[(frame.metric == metric) & (frame.start < hi) & (frame.end > lo)]
            for _, item in intervals.iterrows():
                fig.add_trace(
                    go.Scatter(
                        x=[max(item.start, lo), min(item.end, hi)],
                        y=[name + " " + metric] * 2,
                        mode="lines",
                        line={"width": 8, "color": color},
                        name=name + " " + metric,
                        legendgroup=name + metric,
                        showlegend=False,
                        text=str(item.category),
                        hovertemplate="%{text}<extra></extra>",
                    ),
                    row=3,
                    col=1,
                )
    t = truth[(truth.start < hi) & (truth.end > lo)]
    for _, item in t.iterrows():
        fig.add_trace(
            go.Scatter(
                x=[max(item.start, lo), min(item.end, hi)],
                y=[item.hr_target] * 2,
                mode="lines",
                line={"color": "#999", "width": 1},
                showlegend=False,
                text=str(item.state),
                hovertemplate="Truth target: %{y:.1f} bpm<br>%{text}<extra></extra>",
            ),
            row=1,
            col=1,
        )
    fig.update_xaxes(range=[lo, hi])
    fig.update_yaxes(title_text="bpm", row=1, col=1)
    fig.update_yaxes(title_text="steps/min", row=2, col=1)
    fig.update_layout(height=950, hovermode="closest", title=f"Day explorer · {day}")
    return fig


def _contexts(frame):
    hr = frame[frame.metric == "heart_rate"].copy().sort_values("start")
    hr["context"] = "other / unknown"
    # Sleep and workout are observable contexts. Workout takes precedence.
    for metric in ("sleep", "workout"):
        intervals = frame[frame.metric == metric]
        if metric == "sleep":
            intervals = intervals[intervals.category.fillna("").str.contains("asleep", case=False)]
        for _, item in intervals.iterrows():
            hr.loc[(hr.start >= item.start) & (hr.start < item.end), "context"] = metric
    return hr


def distribution_chart(real, synthetic, context):
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Heart-rate distribution", "Empirical cumulative distribution"))
    samples = []
    for frame, name, color in [(real, "Real", "#1976d2"), (synthetic, "Twin", "#e27624")]:
        hr = _contexts(frame)
        if context != "all":
            hr = hr[hr.context == context]
        values = np.sort(pd.to_numeric(hr.value, errors="coerce").dropna().to_numpy())
        samples.append(values)
        if len(values):
            fig.add_trace(
                go.Histogram(
                    x=values,
                    histnorm="probability density",
                    opacity=0.55,
                    name=f"{name} (n={len(values):,})",
                    marker_color=color,
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Scattergl(
                    x=values,
                    y=np.arange(1, len(values) + 1) / len(values),
                    mode="lines",
                    name=name,
                    line={"color": color},
                    showlegend=False,
                ),
                row=1,
                col=2,
            )
    fig.update_layout(barmode="overlay", height=430)
    fig.update_xaxes(title_text="bpm")
    distance = float(wasserstein_distance(*samples)) if all(len(x) for x in samples) else None
    return fig, distance, [len(x) for x in samples]


def week_chart(real, synthetic, start, end):
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        subplot_titles=("Real: hourly median heart rate", "Twin: hourly median heart rate"),
    )
    for row, frame in enumerate((real, synthetic), 1):
        hr = frame[frame.metric == "heart_rate"].copy()
        if hr.empty:
            continue
        hr["date"] = hr.start.dt.date.astype(str)
        hr["hour"] = hr.start.dt.hour
        grid = hr.pivot_table(index="hour", columns="date", values="value", aggfunc="median").reindex(
            index=range(24), columns=pd.date_range(start, end).strftime("%Y-%m-%d")
        )
        fig.add_trace(
            go.Heatmap(z=grid.values, x=grid.columns, y=grid.index, coloraxis="coloraxis", hoverongaps=False),
            row=row,
            col=1,
        )
    fig.update_layout(height=650, coloraxis={"colorscale": "Viridis", "colorbar": {"title": "bpm"}})
    fig.update_yaxes(title_text="Local hour", autorange="reversed")
    return fig


def workout_chart(real, synthetic):
    fig = go.Figure()
    counts = []
    for name, frame, color in (("Real", real, "#1976d2"), ("Twin", synthetic, "#e27624")):
        workouts = frame[frame.metric == "workout"].sort_values("start").head(30)
        counts.append(len(workouts))
        hr = frame[frame.metric == "heart_rate"].sort_values("start")
        for _, workout in workouts.iterrows():
            window = hr[
                (hr.start >= workout.start - pd.Timedelta(minutes=20))
                & (hr.start <= workout.end + pd.Timedelta(minutes=30))
            ]
            # Do not connect across a gap over five minutes.
            if window.empty:
                continue
            x = (window.start - workout.start).dt.total_seconds() / 60
            y = window.value.copy()
            y.loc[window.start.diff().dt.total_seconds().gt(300)] = np.nan
            fig.add_trace(
                go.Scattergl(
                    x=x,
                    y=y,
                    mode="lines+markers",
                    marker={"size": 3},
                    line={"color": color, "width": 1},
                    opacity=0.45,
                    name=name,
                    legendgroup=name,
                    showlegend=False,
                    text=f"{name} · {workout.start} · {workout.category}",
                    hovertemplate="%{text}<br>%{x:.1f} min · %{y:.1f} bpm<extra></extra>",
                )
            )
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", name=name, legendgroup=name, line={"color": color}))
    fig.add_vline(x=0, line_dash="dash", line_color="gray")
    fig.update_xaxes(title_text="Minutes from workout start")
    fig.update_yaxes(title_text="bpm")
    fig.update_layout(height=430)
    return fig, counts


def slice_window(frame, start, end):
    lo, hi = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    return frame[(frame.start < hi) & ((frame.end > lo) | ((frame.start == frame.end) & (frame.start >= lo)))].copy()


def step_bins(frame, start, end, frequency="D", metric="steps"):
    """Apportion interval step counts across local-time bins, assuming a constant rate.

    Missing bins are NaN; zero-duration records are assigned to their start bin.
    Sources can overlap and are not deduplicated.
    """
    lo, hi = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    edges = pd.date_range(lo, hi, freq=frequency)
    totals = pd.Series(np.nan, index=edges[:-1], dtype=float)
    for item in frame[frame.metric == metric].itertuples():
        if pd.isna(item.value) or item.end < item.start:
            continue
        if item.start == item.end:
            if lo <= item.start < hi:
                idx = edges.searchsorted(item.start, side="right") - 1
                totals.iloc[idx] = (0 if pd.isna(totals.iloc[idx]) else totals.iloc[idx]) + item.value
            continue
        a, b = max(item.start, lo), min(item.end, hi)
        if a >= b:
            continue
        duration = (item.end - item.start).total_seconds()
        first = max(0, edges.searchsorted(pd.Timestamp(a).to_datetime64(), side="right") - 1)
        last = min(len(totals), edges.searchsorted(pd.Timestamp(b).to_datetime64(), side="left"))
        for idx in range(first, last):
            seconds = (min(b, edges[idx + 1]) - max(a, edges[idx])).total_seconds()
            if seconds > 0:
                totals.iloc[idx] = (
                    0 if pd.isna(totals.iloc[idx]) else totals.iloc[idx]
                ) + item.value * seconds / duration
    return totals


def steps_chart(real, synthetic, start, end, day, period):
    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=("Cumulative observed steps on selected day", f"{period.title()} observed step totals"),
    )
    _lo, _hi = pd.Timestamp(start), pd.Timestamp(end)
    totals = {}
    for frame, name, color in ((real, "Real", "#1976d2"), (synthetic, "Twin", "#e27624")):
        hourly = step_bins(frame, day, day, "h")
        # Plot missing bins as gaps; cumulative count resumes without treating missing as observed zero.
        cumulative = hourly.fillna(0).cumsum().where(hourly.notna())
        fig.add_trace(
            go.Scatter(
                x=hourly.index + pd.Timedelta(hours=1),
                y=cumulative,
                mode="lines+markers",
                name=name,
                legendgroup=name,
                line={"color": color},
                connectgaps=False,
            ),
            row=1,
            col=1,
        )
        daily = step_bins(frame, start, end)
        series = daily.resample("W-MON", label="left", closed="left").sum(min_count=1) if period == "weekly" else daily
        totals[name] = (
            int(daily.notna().sum()),
            len(daily),
            float(daily.sum(min_count=1)) if daily.notna().any() else None,
        )
        fig.add_trace(
            go.Bar(x=series.index, y=series.values, name=name, legendgroup=name, marker_color=color, showlegend=False),
            row=2,
            col=1,
        )
    fig.update_layout(height=700, barmode="group")
    fig.update_yaxes(title_text="steps", row=1, col=1)
    fig.update_yaxes(title_text="steps", row=2, col=1)
    return fig, totals


def health_chart(real, synthetic, metric, start, end):
    label, unit, additive = METRIC_INFO[metric]
    day_view = start == end
    fig = go.Figure()
    counts = {}
    for frame, name, color in ((real, "Real", "#1976d2"), (synthetic, "Twin", "#e27624")):
        values = frame[(frame.metric == metric) & frame.value.notna()].copy()
        counts[name] = len(values)
        if additive:
            bins = step_bins(frame, start, end, "h" if day_view else "D", metric=metric)
            fig.add_trace(go.Bar(x=bins.index, y=bins.values, name=name, marker_color=color))
        elif day_view:
            fig.add_trace(
                go.Scattergl(
                    x=values.start,
                    y=values.value,
                    mode="markers",
                    name=name,
                    marker={"color": color, "size": 6},
                    hovertemplate="%{x}<br>%{y:.2f} " + unit + "<extra>%{fullData.name}</extra>",
                )
            )
        elif not values.empty:
            values["day"] = values.start.dt.floor("D")
            summary = values.groupby("day", observed=True).value.agg(["min", "median", "max", "count"])
            # Missing days remain absent rather than being interpolated.
            summary = summary.reindex(pd.date_range(start, end, freq="D"))
            fig.add_trace(
                go.Scatter(
                    x=summary.index,
                    y=summary["median"],
                    mode="markers",
                    name=name,
                    marker={"color": color, "size": 9},
                    error_y={
                        "type": "data",
                        "symmetric": False,
                        "array": summary["max"] - summary["median"],
                        "arrayminus": summary["median"] - summary["min"],
                        "color": color,
                        "thickness": 2,
                    },
                    customdata=summary["count"],
                    hovertemplate="%{x|%Y-%m-%d}<br>median %{y:.2f}<br>n=%{customdata}<extra>%{fullData.name}</extra>",
                )
            )
    fig.update_layout(title=f"{label} · {'day' if day_view else 'daily summaries'}", barmode="group", height=420)
    fig.update_yaxes(title_text=unit)
    if day_view:
        fig.update_xaxes(range=[pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)])
    return fig, counts


def comparison_table(real, synthetic, metric: str):
    sides = []
    for frame in (real, synthetic):
        rows = frame[frame.metric == metric]
        sides.append(
            {
                "Records": len(rows),
                "Median duration (s)": (rows.end - rows.start).dt.total_seconds().median(),
                "Median value": rows.value.median(),
            }
        )
    result = pd.DataFrame({"Real": sides[0], "Synthetic": sides[1]})
    result["Synthetic minus real"] = result["Synthetic"] - result["Real"]
    return result.round(2).rename_axis("Measure").reset_index()


def workout_options(frame):
    workouts = frame[frame.metric == "workout"].sort_values("start").reset_index(drop=True)
    options = {}
    for index, workout in workouts.iterrows():
        minutes = (workout.end - workout.start).total_seconds() / 60
        label = f"{workout.start:%Y-%m-%d %H:%M} · {workout.category or 'workout'} · {minutes:.0f} min · #{index + 1}"
        options[label] = int(index)
    return workouts, options


def single_workout_chart(real, synthetic, real_workouts, twin_workouts, real_choice, twin_choice):
    fig = go.Figure()
    info = []
    for name, frame, workouts, choice, color in (
        ("Real", real, real_workouts, real_choice, "#1976d2"),
        ("Twin", synthetic, twin_workouts, twin_choice, "#e27624"),
    ):
        if choice is None:
            info.append(f"{name}: no workout selected")
            continue
        workout = workouts.iloc[choice]
        hr = frame[
            (frame.metric == "heart_rate")
            & (frame.start >= workout.start - pd.Timedelta(minutes=10))
            & (frame.start <= workout.end + pd.Timedelta(minutes=20))
        ].sort_values("start")
        # Retain the first point after each gap while breaking the connecting line.
        x, y = [], []
        previous = None
        for reading in hr.itertuples():
            if previous is not None and (reading.start - previous).total_seconds() > 300:
                x.append(None)
                y.append(None)
            x.append((reading.start - workout.start).total_seconds() / 60)
            y.append(reading.value)
            previous = reading.start
        fig.add_trace(
            go.Scattergl(
                x=x, y=y, mode="lines+markers", name=name, line={"color": color}, marker={"size": 4}, connectgaps=False
            )
        )
        duration = (workout.end - workout.start).total_seconds() / 60
        fig.add_vline(x=duration, line_dash="dot", line_color=color)
        info.append(f"{name}: {duration:.0f} min, {len(hr):,} HR readings")
    fig.add_vline(x=0, line_dash="dash", line_color="gray")
    fig.update_layout(height=430, xaxis_title="Minutes from workout start", yaxis_title="bpm")
    return fig, info
