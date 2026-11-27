"""The localhost web API: chat -> task, the simulated pipeline, task and notification lists."""

import pytest
from fastapi.testclient import TestClient

from llm_worker.providers.pg import PgDataSource, load_scenarios
from llm_worker.providers.scenarios import load_bundled_store
from llm_worker.semantic import LotusModel
from llm_worker.settings import Settings
from llm_worker.tasks.registry import Deps, build_handlers
from llm_worker.web.app import create_app
from llm_worker.worker import Worker

pytestmark = pytest.mark.integration

STORE = load_bundled_store()


class NoNotifier:
    def notify(self, run, notification):
        pass


@pytest.fixture
def setup(pool, fake_llm):
    with pool.connection() as conn:
        load_scenarios(conn, STORE, batch_id="api-test")
    source = PgDataSource(pool)
    settings = Settings(id="api-test", backoff_seconds=0, llm_model="fake-small", llm_base_url=fake_llm.base_url)
    handlers = build_handlers(Deps(source, LotusModel(base_url=fake_llm.base_url, model="fake-small")))
    client = TestClient(create_app(pool, handlers, source, settings))
    worker = Worker(pool, handlers, NoNotifier(), settings)
    return client, worker


def drain(worker):
    while worker.run_once():
        pass


def chat(client, text, **extra):
    return client.post("/api/chat", json={"text": text, "submitted_by": "doctor", **extra})


def test_the_page_and_the_status_are_served(setup):
    client, _ = setup

    page = client.get("/")
    status = client.get("/api/status").json()

    assert page.status_code == 200 and "Semantic Task Worker" in page.text
    assert status["model"] == "fake-small" and set(status["templates"]) == {
        "alert_triage",
        "patient_explain",
        "cohort_query",
    }


def test_patients_and_demo_prompts_are_listed(setup):
    client, _ = setup

    patients = client.get("/api/patients").json()
    prompts = client.get("/api/demo/prompts").json()

    assert len(patients) == 14 and set(patients[0]) == {"patient_id", "age_band", "sex", "flagged_nights"}
    assert len(prompts) == 12 and {"text", "template", "expect"} <= set(prompts[0])


def test_a_chat_question_is_routed_queued_and_answered(setup):
    client, worker = setup

    created = chat(client, "What happened to P-010 over the last week? Is it getting worse?")
    assert created.status_code == 201
    body = created.json()
    assert (body["template"], body["params"]) == ("patient_explain", {"patient_id": "P-010", "since_days": 7})
    assert client.get(f"/api/tasks/{body['task_id']}").json()["state"] == "pending"

    drain(worker)

    task = client.get(f"/api/tasks/{body['task_id']}").json()
    assert task["state"] == "finished" and task["answer"].startswith("[fake model]")
    assert task["trigger"] == "chat" and task["submitted_by"] == "doctor"


def test_the_chat_cannot_start_an_alert_triage(setup):
    client, _ = setup

    response = chat(client, "Triage this", template="alert_triage", patient_id="P-001")

    assert response.status_code == 403 and "chat" in response.json()["detail"]


def test_bad_chat_input_is_rejected_with_a_reason(setup):
    client, _ = setup

    assert chat(client, "How is P-999?").status_code == 400
    assert chat(client, "").status_code == 422
    assert client.post("/api/chat", json={"text": "x", "submitted_by": "pipeline"}).status_code == 422


def test_asking_the_chat_to_notify_returns_a_notice_and_notifies_nobody(setup):
    client, worker = setup

    body = chat(client, "Notify the doctor about P-014 now.").json()
    drain(worker)

    assert "never notif" in body["notice"]
    assert client.get("/api/notifications").json() == []


def test_the_simulated_pipeline_is_idempotent_and_its_alerts_notify(setup):
    client, worker = setup

    assert client.post("/api/demo/pipeline").json() == {"created": 14, "total": 14}
    assert client.post("/api/demo/pipeline").json() == {"created": 0, "total": 14}
    drain(worker)

    alerts = client.get("/api/tasks", params={"trigger": "pipeline"}).json()
    sent = client.get("/api/notifications").json()
    assert len(alerts) == 14 and all(t["state"] == "finished" for t in alerts)
    assert len(sent) == 9 and {"patient_id", "night_date", "verdict", "explanation", "task_id"} <= set(sent[0])
    assert client.get("/api/tasks", params={"trigger": "chat"}).json() == []


def test_an_unknown_task_is_404(setup):
    client, _ = setup

    assert client.get("/api/tasks/12345").status_code == 404


def test_a_chat_question_with_a_numeric_filter_returns_the_matching_nights_from_the_database(setup, conn):
    client, worker = setup
    fever = [{"signal": "wrist_temp_delta", "op": ">=", "z": 2}]

    body = chat(client, "Which patients have a fever?", filters=fever).json()
    drain(worker)

    task = client.get(f"/api/tasks/{body['task_id']}").json()
    assert body["params"]["filters"] == fever
    flu = next(m for m in task["result"]["matches"] if m["patient_id"] == "P-010")
    for night in flu["evidence"]["nights"]:
        db = conn.execute(
            "SELECT wrist_temp_delta FROM vitals.nightly_features WHERE patient_id = 'P-010' AND night_date = %s",
            (night["night"],),
        ).fetchone()[0]
        temp = next(s for s in night["signals"] if s["signal"] == "wrist_temp_delta")
        assert temp["value"] == db


def test_an_invalid_filter_is_rejected(setup):
    client, _ = setup

    bad = chat(client, "Which patients?", filters=[{"signal": "rhr", "op": "==", "z": 2}])

    assert bad.status_code == 400


def test_the_pipeline_reads_its_candidates_from_the_flags_table(setup, conn):
    client, _ = setup
    conn.execute("DELETE FROM vitals.nightly_flags WHERE patient_id <> 'P-009'")

    assert client.post("/api/demo/pipeline").json() == {"created": 1, "total": 1}
