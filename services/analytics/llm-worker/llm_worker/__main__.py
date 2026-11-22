import argparse
import logging
import signal
import sys
import threading
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from . import repository
from .fake_llm import FakeLLM
from .notify import LogNotifier
from .providers.scenarios import ScenarioStore, load_bundled_store
from .settings import Settings
from .stages import default_stages
from .worker import Worker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llm_worker")
    parser.add_argument("command", choices=["migrate", "seed", "run", "once", "fake-llm"])
    parser.add_argument("--port", type=int, default=8080, help="fake-llm: port to listen on")
    args = parser.parse_args(argv)
    command = args.command

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    if command == "fake-llm":
        return _fake_llm(args.port)

    settings = Settings()

    if command in ("migrate", "seed"):
        with psycopg.connect(settings.dsn, autocommit=True) as conn:
            repository.migrate(conn)
            if command == "seed":
                n = repository.seed(conn, _store(settings))
                logging.getLogger(__name__).info("enqueued %d scenario candidates", n)
        return 0

    with ConnectionPool(settings.dsn, min_size=1, max_size=2, kwargs={"autocommit": True}) as pool:
        worker = Worker(pool, default_stages(settings, store=_store(settings)), LogNotifier(), settings)
        if command == "once":
            while worker.run_once():
                pass
            return 0

        stop = threading.Event()
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: stop.set())
        worker.run(stop)
    return 0


def _store(settings: Settings) -> ScenarioStore:
    return ScenarioStore.from_dir(Path(settings.scenarios_dir)) if settings.scenarios_dir else load_bundled_store()


def _fake_llm(port: int) -> int:
    """OpenAI-compatible stand-in for the model, for running the worker without Ollama (compose profile `stub`)."""
    server = FakeLLM(host="0.0.0.0", port=port)
    logging.getLogger(__name__).info("fake LLM listening on %s", server.base_url)
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    stop.wait()
    server.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
