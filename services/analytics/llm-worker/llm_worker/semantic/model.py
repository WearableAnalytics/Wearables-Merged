"""Connection from LOTUS to a language model behind an OpenAI-compatible endpoint (plan §5).

Local: Ollama (`http://localhost:11434/v1`). Cluster: Ollama / vLLM on OpenStack. Tests: llm_worker.fake_llm.
Only the URL, model name and key differ; the code path is the same. This is the only module that imports lotus.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

# No outbound calls at import time (LiteLLM's remote price list, Hugging Face downloads): data stays in the network.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
os.environ.setdefault("HF_HUB_OFFLINE", "1")


class LLMUnavailable(RuntimeError):
    """The model endpoint failed. The candidate is retried later; nothing is written as a result."""


@functools.cache
def _lm_class():
    import litellm
    from lotus.models import LM

    litellm.telemetry = False
    litellm.suppress_debug_info = True

    class CheckedLM(LM):
        """LiteLLM returns transport failures inside the response list; turn them into one exception."""

        def _process_uncached_messages(self, uncached_data, all_kwargs, show_progress_bar, progress_bar_desc):
            responses = super()._process_uncached_messages(
                uncached_data, all_kwargs, show_progress_bar, progress_bar_desc
            )
            for response in responses:
                if isinstance(response, Exception):
                    raise LLMUnavailable(f"{type(response).__name__}: {response}") from response
            return responses

    return CheckedLM


@dataclass(frozen=True)
class LotusModel:
    base_url: str
    model: str
    api_key: str = "unused"
    max_batch_size: int = 8  # concurrent calls per LOTUS batch; align with the server's concurrency
    timeout_seconds: float = 120.0

    @contextmanager
    def session(self, max_tokens: int) -> Iterator[None]:
        """LOTUS settings for one operator call: temperature 0, no cache, no retries inside LiteLLM."""
        import lotus

        lm = _lm_class()(
            model=f"openai/{self.model}",
            api_base=self.base_url,
            api_key=self.api_key,
            temperature=0.0,
            max_tokens=max_tokens,
            max_batch_size=self.max_batch_size,
            timeout=self.timeout_seconds,
            num_retries=0,
        )
        try:
            with lotus.settings.context(lm=lm, enable_cache=False):
                yield
        except LLMUnavailable:
            raise
        except Exception as exc:  # connection errors raised by LiteLLM before LOTUS sees a response
            if _is_transport_error(exc):
                raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc
            raise


def _is_transport_error(exc: Exception) -> bool:
    import litellm

    transport = (
        litellm.APIConnectionError,
        litellm.APIError,
        litellm.Timeout,
        litellm.ServiceUnavailableError,
        litellm.InternalServerError,
    )
    return isinstance(exc, transport)
