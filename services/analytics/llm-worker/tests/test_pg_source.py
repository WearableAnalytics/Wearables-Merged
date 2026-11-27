"""Mock gold serving tables in PostgreSQL (`vitals`, `patient_context`) and the provider that reads them.

Contract: the PostgreSQL source returns exactly what the scenario source returns; the handlers cannot tell them apart.
The real gold sync (Spark -> staging -> commit_batch) later fills the same tables.
"""

from datetime import timedelta

import pytest

from llm_worker.providers import as_of_for
from llm_worker.providers.pg import PgDataSource, load_scenarios
from llm_worker.providers.scenarios import load_bundled_store
from llm_worker.tasks.model import NumericCondition

pytestmark = pytest.mark.integration

STORE = load_bundled_store()


@pytest.fixture
def source(pool):
    with pool.connection() as conn:
        load_scenarios(conn, STORE, batch_id="test-batch")
    return PgDataSource(pool)


def without_source(dto):
    return dto.model_copy(update={"source": "-"})


def test_loading_writes_one_committed_batch_and_the_serving_rows(source, conn):
    batch = conn.execute("SELECT batch_id, status, night_from, night_to FROM vitals.sync_batches").fetchall()
    features = conn.execute("SELECT count(*) FROM vitals.nightly_features").fetchone()[0]
    entries = conn.execute("SELECT count(*) FROM patient_context.entries").fetchone()[0]

    assert [(b[0], b[1], b[3]) for b in batch] == [("test-batch", "committed", STORE.today)]
    assert features == 14 * 31  # every patient, the last 31 nights
    assert entries == sum(len(STORE.get(n).context) for n in STORE.names())


def test_loading_again_replaces_the_data_instead_of_duplicating_it(source, conn):
    load_scenarios(conn, STORE, batch_id="second-batch")

    assert conn.execute("SELECT count(*) FROM vitals.nightly_features").fetchone()[0] == 14 * 31
    assert conn.execute("SELECT count(*) FROM vitals.sync_batches WHERE status = 'committed'").fetchone()[0] == 2


def test_patients_candidates_and_latest_night_match_the_scenarios(source):
    assert source.today == STORE.today
    assert source.patient_ids() == STORE.patient_ids()
    assert source.patients() == STORE.patients()
    assert source.all_candidates() == STORE.all_candidates()
    assert source.has_patient("P-010") and not source.has_patient("P-999")


def test_numeric_context_from_postgres_equals_the_scenario_one_for_every_patient_and_night(source):
    for pid in STORE.patient_ids():
        for d in range(15):
            night = STORE.today - timedelta(days=d)
            assert without_source(source.numeric.get(pid, night)) == without_source(STORE.numeric.get(pid, night)), (
                pid,
                night,
            )


def test_descriptive_context_from_postgres_equals_the_scenario_one(source):
    for c in STORE.all_candidates():
        as_of = as_of_for(c.night_date)
        got = source.descriptive.get(c.patient_id, c.night_date, as_of)
        assert without_source(got) == without_source(STORE.descriptive.get(c.patient_id, c.night_date, as_of))


def test_the_future_and_unknown_patients_are_not_served(source):
    with pytest.raises(LookupError):
        source.numeric.get("P-010", STORE.today + timedelta(days=1))
    with pytest.raises(LookupError):
        source.numeric.get("P-999", STORE.today)
    with pytest.raises(LookupError):
        source.descriptive.get("P-999", STORE.today, as_of_for(STORE.today))


@pytest.mark.parametrize(
    ("conditions", "match"),
    [
        ([NumericCondition(signal="wrist_temp_delta", op=">=", z=2)], "any"),
        (
            [NumericCondition(signal="resp_rate", op=">=", z=2), NumericCondition(signal="spo2_mean", op="<=", z=-2)],
            "all",
        ),
        ([NumericCondition(signal="rhr", op="<=", z=-2)], "any"),
        ([NumericCondition(signal="rhr", op=">=", z=2), NumericCondition(signal="hrv_sdnn", op="<=", z=-2)], "any"),
    ],
)
def test_the_numeric_predicate_runs_as_sql_and_matches_the_scenario_source(source, conditions, match):
    sql = source.nights_matching(conditions, match, since_days=7)

    assert sql == STORE.nights_matching(conditions, match, since_days=7)
    assert sql  # every case matches something in the mock data


def test_the_numeric_predicate_can_be_limited_to_one_patient(source):
    fever = [NumericCondition(signal="wrist_temp_delta", op=">=", z=2)]

    nights = source.nights_matching(fever, "any", since_days=7, patient_id="P-010")

    assert [(p, n.isoformat()) for p, n in nights] == [
        ("P-010", "2026-03-11"),
        ("P-010", "2026-03-12"),
        ("P-010", "2026-03-13"),
        ("P-010", "2026-03-14"),
    ]
