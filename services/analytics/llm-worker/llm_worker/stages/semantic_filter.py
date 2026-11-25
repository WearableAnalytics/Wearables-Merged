import time
from collections.abc import Callable

from psycopg import Connection

from ..pipeline import Context


class SemanticFilter:
    """Stand-in for L3: decides whether a documented, benign cause explains the night.

    Red flags never reach the model and can never be explained away.
    """

    name = "semantic_filter"

    def __init__(self, seconds: float, sleep: Callable[[float], None] = time.sleep):
        self.seconds = seconds
        self.sleep = sleep

    def run(self, ctx: Context, conn: Connection) -> dict:
        if ctx.event.red_flag:
            return {"skipped": "red_flag"}

        self.sleep(self.seconds)
        return {"explained": False, "cause": None}
