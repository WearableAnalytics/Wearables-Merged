"""Checks for local-time windows and observable comparison contexts."""

import io
import tarfile
from datetime import date

import pytest

pytest.importorskip("pandas")
pytest.importorskip("plotly")
pytest.importorskip("scipy")

from persona_gen.validation.explorer import distribution_chart, real_records, week_chart


def test_export_window_and_empty_charts(tmp_path):
    xml = b"""<HealthData>
      <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch"
        startDate="2026-08-01 23:50:00 +0200"
        endDate="2026-08-01 23:50:00 +0200" value="70"/>
      <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch"
        startDate="2026-07-31 23:00:00 +0200"
        endDate="2026-08-01 07:00:00 +0200"
        value="HKCategoryValueSleepAnalysisAsleepCore"/>
      <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="iPhone"
        startDate="2026-08-01 12:00:00 +0200"
        endDate="2026-08-01 12:00:00 +0200" value="90"/>
      <Workout sourceName="Other"
        startDate="2026-08-01 18:00:00 +0200"
        endDate="2026-08-01 19:00:00 +0200" workoutActivityType="run"/>
    </HealthData>"""
    path = tmp_path / "export.tar.xz"
    with tarfile.open(path, "w:xz") as tar:
        info = tarfile.TarInfo("apple_health_export/export.xml")
        info.size = len(xml)
        tar.addfile(info, io.BytesIO(xml))
    day = date(2026, 8, 1)
    records = real_records(path, "apple_watch", day, day)
    assert records.metric.tolist() == ["heart_rate", "sleep", "workout"]
    assert records.iloc[0].start.hour == 23
    empty = real_records(path, "apple_watch", date(2026, 8, 3), date(2026, 8, 3))
    _, distance, counts = distribution_chart(records, empty, "all")
    assert distance is None and counts == [1, 0]
    assert len(week_chart(records, empty, day, day).data) == 1


def test_context_filters_overlaid_heart_rates_and_step_apportionment():
    import pandas as pd

    from persona_gen.validation.explorer import day_chart, slice_window, step_bins, steps_chart

    columns = ["metric", "start", "end", "value", "category", "source"]
    records = pd.DataFrame(
        [
            ("heart_rate", "2026-08-01 06:00", "2026-08-01 06:00", 60, None, "watch"),
            ("heart_rate", "2026-08-01 12:00", "2026-08-01 12:00", 110, None, "watch"),
            ("sleep", "2026-08-01 00:00", "2026-08-01 07:00", None, "asleep_core", "watch"),
            ("steps", "2026-08-01 23:30", "2026-08-02 00:30", 120, None, "watch"),
            ("steps", "2026-08-02 12:00", "2026-08-02 12:00", 5, None, "watch"),
        ],
        columns=columns,
    )
    records["start"] = pd.to_datetime(records.start)
    records["end"] = pd.to_datetime(records.end)
    start, end = date(2026, 8, 1), date(2026, 8, 3)
    bins = step_bins(records, start, end)
    assert bins.iloc[0] == 60 and bins.iloc[1] == 65 and pd.isna(bins.iloc[2])
    assert (
        step_bins(slice_window(records, date(2026, 8, 2), date(2026, 8, 2)), date(2026, 8, 2), date(2026, 8, 2)).iloc[0]
        == 65
    )
    truth = pd.DataFrame({"start": pd.to_datetime([]), "end": pd.to_datetime([]), "hr_target": [], "state": []})
    chart = day_chart(records, records, truth, start, "sleep")
    traces = [trace for trace in chart.data if trace.name in ("Real HR", "Twin HR")]
    assert len(traces) == 2 and all(list(trace.y) == [60] for trace in traces)
    assert traces[0].yaxis == traces[1].yaxis
    _, totals = steps_chart(records, records, start, end, start, "weekly")
    assert totals["Real"] == (2, 3, 125.0)


def test_oxygen_units_and_selected_workouts(tmp_path):
    import pandas as pd

    from persona_gen.validation.explorer import health_chart, single_workout_chart, workout_options

    xml = b"""<HealthData>
      <Record type="HKQuantityTypeIdentifierOxygenSaturation" sourceName="Watch"
        startDate="2026-08-01 12:00:00 +0200" endDate="2026-08-01 12:00:00 +0200" value="0.97" unit="%"/>
      <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch"
        startDate="2026-08-01 12:10:00 +0200" endDate="2026-08-01 12:10:00 +0200" value="120"/>
      <Workout sourceName="Watch" startDate="2026-08-01 12:00:00 +0200"
        endDate="2026-08-01 12:30:00 +0200" workoutActivityType="Run"/>
    </HealthData>"""
    path = tmp_path / "export.tar.xz"
    with tarfile.open(path, "w:xz") as tar:
        info = tarfile.TarInfo("export.xml")
        info.size = len(xml)
        tar.addfile(info, io.BytesIO(xml))
    day = date(2026, 8, 1)
    records = real_records(path, "apple_watch", day, day)
    assert records.loc[records.metric == "oxygen_saturation", "value"].iloc[0] == 97
    chart, counts = health_chart(records, records, "oxygen_saturation", day, day)
    assert counts == {"Real": 1, "Twin": 1}
    assert all(list(trace.y) == [97] for trace in chart.data)
    workouts, _ = workout_options(records)
    chart, _ = single_workout_chart(records, records, workouts, workouts, 0, 0)
    assert len(chart.data) == 2
    assert all(list(trace.x) == [10] and list(trace.y) == [120] for trace in chart.data)
    empty = records.iloc[:0].copy()
    assert pd.isna(health_chart(empty, empty, "steps", day, day)[0].data[0].y[0])
