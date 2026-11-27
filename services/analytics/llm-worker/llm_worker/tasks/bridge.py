"""The data pipeline's side: a suspicious event (alert candidate) becomes an `alert_triage` task with its own prompt.

In the MVP the "pipeline" reads the flagged nights of the mock serving tables; later `alerting.alert_candidates`.
"""

from ..dto import AlertCandidate
from ..providers import DataSource
from .model import TaskRequest


def alert_request(c: AlertCandidate) -> TaskRequest:
    night = c.night_date.isoformat()
    reasons = ", ".join(c.trigger_reasons) or "unknown rules"
    red = " RED FLAG: a safety threshold was crossed." if c.red_flag else ""
    return TaskRequest(
        template="alert_triage",
        params={
            "patient_id": c.patient_id,
            "night": night,
            "trigger_reasons": list(c.trigger_reasons),
            "red_flag": c.red_flag,
            "l2_score": c.l2_score,
        },
        prompt=(
            f"Night {night} of {c.patient_id} was flagged by {reasons}.{red} "
            "Does a documented benign cause explain it? Explain the decision for the physician."
        ),
        trigger="pipeline",
        submitted_by="pipeline",
        dedup_key=f"alert_triage:{c.patient_id}:{night}",
    )


def pipeline_requests(source: DataSource) -> list[TaskRequest]:
    return [alert_request(c) for c in source.all_candidates()]
