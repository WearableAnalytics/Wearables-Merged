from psycopg import Connection

from ..evidence import MAX_CONTEXT_ITEMS, gather
from ..pipeline import Context
from ..providers import DescriptiveContextProvider, NumericContextProvider
from ..render import RENDER_VERSION, render


class LoadEvidence:
    """Numbers (gold) + text (patient context) for each candidate, rendered for the semantic operators."""

    name = "load_evidence"

    def __init__(
        self,
        numeric: NumericContextProvider,
        descriptive: DescriptiveContextProvider,
        max_items: int = MAX_CONTEXT_ITEMS,
    ):
        self.numeric, self.descriptive, self.max_items = numeric, descriptive, max_items

    def run(self, batch: list[Context], conn: Connection | None) -> list[dict]:
        outputs = []
        for ctx in batch:
            try:
                ctx.bundle = gather(ctx.event.to_candidate(), self.numeric, self.descriptive, self.max_items)
            except LookupError as exc:
                ctx.error = f"no evidence: {exc}"
                outputs.append({"error": ctx.error})
                continue
            ctx.rendered = render(ctx.bundle)
            outputs.append(
                {
                    "facts": len(ctx.bundle.numeric.tonight),
                    "context_items": len(ctx.bundle.descriptive.items),
                    "render": RENDER_VERSION,
                    **ctx.bundle.provenance,
                }
            )
        return outputs
