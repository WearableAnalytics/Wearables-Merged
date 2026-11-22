"""Gathering evidence: numbers and text are fetched independently (in parallel) and joined into one bundle."""

import threading
from datetime import date

import pytest

from llm_worker.dto import AlertCandidate, DescriptiveContext, NumericContext
from llm_worker.evidence import gather
from llm_worker.providers import as_of_for
from llm_worker.providers.scenarios import load_bundled_store

NIGHT = date(2026, 3, 14)


def candidate(**overrides) -> AlertCandidate:
    return AlertCandidate(**({"candidate_id": 7, "patient_id": "P-001", "night_date": NIGHT} | overrides))


class BarrierNumeric:
    """Both providers wait on the same barrier: the test only passes if they run at the same time."""

    def __init__(self, barrier, inner):
        self.barrier, self.inner = barrier, inner

    def get(self, patient_id, night_date):
        self.barrier.wait()
        return self.inner.get(patient_id, night_date)


class BarrierDescriptive(BarrierNumeric):
    def get(self, patient_id, night_date, as_of, max_items=20):
        self.barrier.wait()
        return self.inner.get(patient_id, night_date, as_of, max_items=max_items)


def test_gather_fetches_numbers_and_text_in_parallel():
    store = load_bundled_store()
    barrier = threading.Barrier(2, timeout=5)

    bundle = gather(candidate(), BarrierNumeric(barrier, store.numeric), BarrierDescriptive(barrier, store.descriptive))

    assert isinstance(bundle.numeric, NumericContext)
    assert isinstance(bundle.descriptive, DescriptiveContext)
    assert bundle.candidate.candidate_id == 7


def test_gather_records_provenance():
    store = load_bundled_store()

    bundle = gather(candidate(), store.numeric, store.descriptive)

    assert bundle.provenance["as_of"] == as_of_for(NIGHT).isoformat()
    assert bundle.provenance["numeric_source"].startswith("scenario:")
    assert bundle.provenance["descriptive_source"].startswith("scenario:")
    assert "truncated_context_items" in bundle.provenance


def test_gather_propagates_a_missing_patient():
    store = load_bundled_store()

    with pytest.raises(LookupError):
        gather(candidate(patient_id="nobody"), store.numeric, store.descriptive)
