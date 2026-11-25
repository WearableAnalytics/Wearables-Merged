import time
from collections.abc import Callable

from psycopg import Connection

from ..pipeline import Context


class Explain:
    """Stand-in for L4: turns the numbers and the patient context into a short explanation."""

    name = "explain"

    def __init__(self, seconds: float, sleep: Callable[[float], None] = time.sleep):
        self.seconds = seconds
        self.sleep = sleep

    def run(self, ctx: Context, conn: Connection) -> dict:
        self.sleep(self.seconds)
        ctx.explanation = render(ctx)
        return {"model": "stub", "length": len(ctx.explanation)}


def render(ctx: Context) -> str:
    event = ctx.event
    numbers = ", ".join(f"{name}={value}" for name, value in sorted(event.features.items())) or "no features"
    diary = len(ctx.patient.get("diary", []))
    entries = "entry" if diary == 1 else "entries"

    if event.red_flag:
        verdict = "Red flag: needs clinician review regardless of context."
    elif ctx.result.get("semantic_filter", {}).get("explained"):
        verdict = "A documented benign cause may explain this night."
    else:
        verdict = "No documented benign cause found. Recommend clinician review."

    return (
        f"[stub] Night of {event.night_date.isoformat()} flagged by {event.reasons or 'unknown reason'} "
        f"({numbers}). Checked {diary} diary {entries}. {verdict}"
    )
