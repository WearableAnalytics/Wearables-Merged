import time
from collections.abc import Callable

from ..pipeline import Stage
from ..settings import Settings
from .context import LoadContext
from .explain import Explain
from .semantic_filter import SemanticFilter


def default_stages(settings: Settings, sleep: Callable[[float], None] = time.sleep) -> list[Stage]:
    half = settings.work_seconds / 2
    return [
        LoadContext(),
        SemanticFilter(seconds=half, sleep=sleep),
        Explain(seconds=half, sleep=sleep),
    ]
