"""Join numbers and text for one candidate. The two sources are independent, so they are fetched in parallel."""

from concurrent.futures import ThreadPoolExecutor

from .dto import AlertCandidate, EvidenceBundle
from .providers import DescriptiveContextProvider, NumericContextProvider, as_of_for

MAX_CONTEXT_ITEMS = 20

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="evidence")


def gather(
    candidate: AlertCandidate,
    numeric: NumericContextProvider,
    descriptive: DescriptiveContextProvider,
    max_items: int = MAX_CONTEXT_ITEMS,
) -> EvidenceBundle:
    as_of = as_of_for(candidate.night_date)
    numbers = _pool.submit(numeric.get, candidate.patient_id, candidate.night_date)
    text = _pool.submit(descriptive.get, candidate.patient_id, candidate.night_date, as_of, max_items=max_items)
    numeric_context, descriptive_context = numbers.result(), text.result()

    return EvidenceBundle(
        candidate=candidate,
        numeric=numeric_context,
        descriptive=descriptive_context,
        provenance={
            "as_of": as_of.isoformat(),
            "numeric_source": numeric_context.source,
            "descriptive_source": descriptive_context.source,
            "sync_batch_id": candidate.sync_batch_id,
            "truncated_context_items": descriptive_context.truncated,
        },
    )
