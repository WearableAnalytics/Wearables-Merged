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


def test_bundled_scenarios_are_fourteen_patients_and_every_candidate_has_an_expected_verdict(store):
    assert {"vaccination_documented", "alcohol_undocumented", "red_flag", "future_note_leak"} <= set(store.names())
    assert len(store.patient_ids()) == 14
    for name in store.names():
        for candidate, verdict in store.get(name).expected():
            assert isinstance(candidate, AlertCandidate)
            assert verdict in {"notify", "suppress", "red_flag_bypass"}


def test_a_patient_can_have_several_candidates_or_none(store):
    flu = store.patient("P-010")
    assert [c.night_date for c in flu.candidates()] == [date(2026, 3, 12), NIGHT]
    assert store.patient("P-014").candidates() == []


def test_all_candidates_are_listed_in_patient_and_night_order(store):
    candidates = store.all_candidates()

    assert len(candidates) == 14  # 13 patients with one or two flagged nights, P-014 has none
    keys = [(c.patient_id, c.night_date) for c in candidates]
    assert keys == sorted(keys)


def test_the_store_knows_its_latest_night(store):
    assert store.today == NIGHT


def test_patients_are_described_by_age_band_and_sex_only(store):
    patients = store.patients()

    assert [p["patient_id"] for p in patients] == store.patient_ids()
    assert patients[0] == {"patient_id": "P-001", "age_band": "50–70", "sex": "F", "flagged_nights": ["2026-03-14"]}


def test_the_older_single_candidate_format_still_loads(tmp_path):
    (tmp_path / "one.yaml").write_text(
        """
name: one
summary: x
patient: {id: P-100, birth_year: 1980, sex: F}
baseline: {rhr: 60}
candidate: {night: 2026-03-14, trigger_reasons: [rhr_z>2]}
expect: {verdict: notify}
""",
        encoding="utf-8",
    )
    store = ScenarioStore.from_dir(tmp_path)

    [(candidate, verdict)] = store.get("one").expected()
    assert (candidate.patient_id, candidate.night_date, verdict) == ("P-100", NIGHT, "notify")


def test_numeric_context_exists_for_any_night_up_to_the_latest(store):
    earlier = store.numeric.get("P-010", date(2026, 3, 11))

    assert earlier.fact("wrist_temp_delta").value == 0.4
    with pytest.raises(LookupError):
        store.numeric.get("P-010", date(2026, 3, 15))


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
