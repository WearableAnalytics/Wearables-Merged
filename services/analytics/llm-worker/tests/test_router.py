"""Chat text -> task request, by rules (no model): a patient means patient_explain, otherwise cohort_query."""

import pytest

from llm_worker.providers.scenarios import load_bundled_store
from llm_worker.tasks.demo import DEMO_PROMPTS
from llm_worker.tasks.router import RouteError, route

PATIENTS = set(load_bundled_store().patient_ids())


def routed(text, **kwargs):
    return route(text, submitted_by="doctor", known_patients=PATIENTS, **kwargs)


def test_a_patient_id_in_the_text_asks_about_that_patient():
    r = routed("What happened to p-010 over the last week?").request

    assert (r.template, r.params, r.trigger, r.submitted_by) == (
        "patient_explain",
        {"patient_id": "P-010", "since_days": 7},
        "chat",
        "doctor",
    )
    assert r.prompt == "What happened to p-010 over the last week?"


def test_the_selected_patient_wins_over_the_text():
    assert routed("Is she improving?", patient_id="P-011").request.params["patient_id"] == "P-011"


def test_no_patient_means_a_question_across_all_patients():
    r = routed("Which patients travelled recently?").request

    assert (r.template, r.params) == ("cohort_query", {"since_days": 7})


@pytest.mark.parametrize(
    ("text", "days"),
    [
        ("Summarise P-014's last two weeks", 14),
        ("P-001 over the last 3 nights", 3),
        ("P-001 in the past 10 days", 10),
        ("P-001 over 40 days", 14),
        ("P-001 last week", 7),
        ("P-001 yesterday", 7),
    ],
)
def test_the_time_window_is_read_from_the_text_and_capped(text, days):
    assert routed(text).request.params["since_days"] == days


def test_an_unknown_patient_is_an_error_not_a_silent_cohort_query():
    with pytest.raises(RouteError, match="P-999"):
        routed("How is P-999?")


def test_empty_text_is_an_error():
    with pytest.raises(RouteError):
        routed("   ")


def test_asking_the_chat_to_notify_creates_a_read_only_task_and_says_so():
    r = routed("Notify the doctor about P-014 now.")

    assert r.request.template == "patient_explain"
    assert r.notice and "never notif" in r.notice


def test_an_explicit_template_is_passed_through_for_the_submit_rules_to_check():
    assert routed("x", template="alert_triage", patient_id="P-001").request.template == "alert_triage"
    with pytest.raises(RouteError, match="patient"):
        routed("x", template="patient_explain")


def test_every_demo_prompt_routes_to_its_documented_template():
    for demo in DEMO_PROMPTS:
        assert routed(demo["text"], filters=demo.get("filters")).request.template == demo["template"], demo["text"]


FEVER = [{"signal": "wrist_temp_delta", "op": ">=", "z": 2}]


def test_numeric_filters_from_the_form_go_into_a_cohort_query():
    r = routed("Which of them get worse over several nights?", filters=FEVER, match="all").request

    assert r.template == "cohort_query"
    assert r.params == {"since_days": 7, "filters": FEVER, "match": "all"}


def test_numeric_filters_with_a_patient_are_an_error_not_silently_dropped():
    with pytest.raises(RouteError, match="filter"):
        routed("How is P-010?", filters=FEVER)
