from pathlib import Path

from ..providers.scenarios import ScenarioStore, load_bundled_store
from ..semantic import LotusModel, build_operator, load_spec
from ..settings import Settings
from .evidence import LoadEvidence
from .explain import Explain
from .triage import SemanticTriage

RENDERED_COLUMNS = {"numeric", "context"}


def default_stages(settings: Settings, store: ScenarioStore | None = None) -> list:
    """Evidence -> L3 triage (sem_filter) -> L4 explanation (sem_map).

    The evidence sources are mocked by scenario fixtures until the gold sync and patient context are decided;
    swap `store.numeric` / `store.descriptive` for the real providers without touching the other stages.
    """
    if store is None:
        store = ScenarioStore.from_dir(Path(settings.scenarios_dir)) if settings.scenarios_dir else load_bundled_store()
    model = LotusModel(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        max_batch_size=settings.llm_concurrency,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    return [
        LoadEvidence(store.numeric, store.descriptive),
        SemanticTriage(build_operator(load_spec("triage"), RENDERED_COLUMNS), model),
        Explain(build_operator(load_spec("explain"), RENDERED_COLUMNS | {"decision"}), model),
    ]
