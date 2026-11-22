"""Mocked data sources: scenario YAML files stand in for the gold serving tables (numbers) and patient_context (text).

The behaviour tested here is the provider contract that the real PostgreSQL / Delta providers must keep later.
"""

from datetime import date, datetime

import pytest

from llm_worker.dto import AlertCandidate, NumericContext
from llm_worker.providers import as_of_for
from llm_worker.providers.scenarios import ScenarioStore, load_bundled_store

NIGHT = date(2026, 3, 14)


@pytest.fixture(scope="module")
def store() -> ScenarioStore:
    return load_bundled_store()


def test_bundled_scenarios_each_have_one_candidate_and_an_expected_verdict(store):
    names = store.names()
    assert {"vaccination_documented", "alcohol_undocumented", "red_flag", "future_note_leak"} <= set(names)
    for name in names:
        scenario = store.get(name)
        assert isinstance(scenario.candidate(candidate_id=1), AlertCandidate)
        assert scenario.expect_verdict in {"notify", "suppress", "red_flag_bypass"}


def test_numeric_context_has_signed_z_against_the_personal_baseline(store):
    numeric = store.numeric.get("P-001", NIGHT)

    assert isinstance(numeric, NumericContext)
    rhr = numeric.fact("rhr")
    assert (rhr.id, rhr.value, rhr.baseline, rhr.unit) == ("n:rhr", 70.0, 62.0, "bpm")
    assert rhr.z == pytest.approx(2.7, abs=0.05)
    hrv = numeric.fact("hrv_sdnn")
    assert hrv.z < 0  # a drop keeps its sign


def test_numeric_context_carries_the_previous_nights_for_persistence(store):
    numeric = store.numeric.get("P-001", NIGHT)

    assert len(numeric.window) == 14
    assert numeric.window[-1].night_date == date(2026, 3, 13)
    assert numeric.fact("rhr").previous == [62.0, 62.0, 62.0]  # D-1, D-2, D-3


def test_missing_signals_stay_missing_instead_of_being_filled(store):
    numeric = store.numeric.get(store.get("missing_coverage").patient_id, NIGHT)

    spo2 = numeric.fact("spo2_mean")
    assert spo2.value is None and spo2.z is None
    assert numeric.coverage["spo2_mean"] < 0.5


def test_unknown_patient_night_raises_lookup_error(store):
    with pytest.raises(LookupError):
        store.numeric.get("nobody", NIGHT)


def test_descriptive_context_never_contains_text_written_after_the_night(store):
    scenario = store.get("future_note_leak")

    context = store.descriptive.get(scenario.patient_id, NIGHT, as_of_for(NIGHT))

    assert all(item.ts is None or item.ts < as_of_for(NIGHT) for item in context.items)
    assert not any("flu shot" in item.text.lower() for item in context.items)


def test_descriptive_context_reports_age_band_sex_and_relative_days(store):
    context = store.descriptive.get("P-001", NIGHT, as_of_for(NIGHT))

    assert (context.age_band, context.sex) == ("50–70", "F")
    note = next(item for item in context.items if "flu shot" in item.text.lower())
    assert note.id.startswith("c:") and note.days_before == 1


def test_long_context_is_truncated_to_the_most_recent_items(store):
    scenario = store.get("long_context_truncation")

    context = store.descriptive.get(scenario.patient_id, NIGHT, as_of_for(NIGHT), max_items=20)

    assert len(context.items) == 20
    assert context.truncated > 0
    newest = max(item.ts for item in context.items if item.ts)
    assert newest == max(item.ts for item in scenario.context_items() if item.ts and item.ts < as_of_for(NIGHT))


def test_as_of_is_noon_after_the_night():
    assert as_of_for(NIGHT) == datetime(2026, 3, 15, 12, 0)
