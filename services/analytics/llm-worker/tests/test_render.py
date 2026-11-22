"""Rendering an evidence bundle into the text columns the semantic operators read (plan §7.2)."""

from datetime import date

import pytest

from llm_worker.evidence import gather
from llm_worker.providers.scenarios import load_bundled_store
from llm_worker.render import RENDER_VERSION, render

NIGHT = date(2026, 3, 14)


@pytest.fixture(scope="module")
def store():
    return load_bundled_store()


def bundle_for(store, name):
    return gather(store.get(name).candidate(candidate_id=1), store.numeric, store.descriptive)


def test_every_fact_and_context_item_is_labelled_with_its_id(store):
    bundle = bundle_for(store, "vaccination_documented")

    row = render(bundle)

    for evidence_id in bundle.evidence_ids():
        assert evidence_id in row.numeric or evidence_id in row.context
    assert row.ids == bundle.evidence_ids()


def test_numbers_show_value_baseline_signed_z_and_previous_nights(store):
    row = render(bundle_for(store, "vaccination_documented"))

    assert "n:rhr" in row.numeric
    line = next(line for line in row.numeric.splitlines() if line.startswith("n:rhr"))
    assert "70 bpm" in line and "baseline 62" in line and "z=+2.7" in line and "D-1 62" in line
    hrv = next(line for line in row.numeric.splitlines() if line.startswith("n:hrv_sdnn"))
    assert "z=-1.1" in hrv


def test_missing_values_are_written_as_missing_with_coverage(store):
    row = render(bundle_for(store, "missing_coverage"))

    spo2 = next(line for line in row.numeric.splitlines() if line.startswith("n:spo2_mean"))
    assert "missing" in spo2
    assert "coverage 20%" in spo2


def test_context_uses_days_relative_to_the_night_not_dates(store):
    row = render(bundle_for(store, "vaccination_documented"))

    note = next(line for line in row.context.splitlines() if "flu shot" in line)
    assert note.startswith("c:104") and "(D-1, note)" in note
    assert "2026-03-13" not in row.context


def test_header_has_age_band_sex_and_trigger_but_no_patient_id(store):
    row = render(bundle_for(store, "vaccination_documented"))

    assert "50–70" in row.numeric and "female" in row.numeric
    assert "flagged by: rhr_z>2" in row.numeric
    assert "P-001" not in row.numeric + row.context  # identifiers never go into prompts


def test_empty_context_is_said_explicitly(store):
    bundle = bundle_for(store, "alcohol_undocumented")
    bundle = bundle.model_copy(update={"descriptive": bundle.descriptive.model_copy(update={"items": []})})

    assert render(bundle).context.strip() == "No documented context."


def test_render_is_deterministic_and_versioned(store):
    bundle = bundle_for(store, "misleading_note")

    assert render(bundle) == render(bundle)
    assert RENDER_VERSION.startswith("render.v")
