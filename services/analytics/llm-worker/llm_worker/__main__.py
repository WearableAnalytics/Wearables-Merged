import argparse
import logging
import signal
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from .fake_llm import FakeLLM
from .notify import LogNotifier
from .providers.pg import PgDataSource, load_scenarios
from .providers.scenarios import ScenarioStore, load_bundled_store
from .settings import Settings
from .stages import model_from
from .tasks import repository, service
from .tasks.registry import Deps, build_handlers
from .worker import Worker

COMMANDS = {
    "migrate": "create the tasks schema",
    "load-mock": "write the scenario fixtures into the mock gold serving tables (vitals, patient_context)",
    "simulate": "act as the data pipeline: one alert_triage task per flagged night (idempotent)",
    "run": "run the worker until stopped",
    "once": "run the worker until the queue is empty",
    "web": "serve the demo page and API on WORKER_WEB_HOST:WORKER_WEB_PORT",
    "fake-llm": "OpenAI-compatible stand-in for the model",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llm_worker", epilog="; ".join(f"{k}: {v}" for k, v in COMMANDS.items()))
    parser.add_argument("command", choices=[*COMMANDS, "seed"])  # seed: old name of simulate
    parser.add_argument("--port", type=int, default=8080, help="fake-llm: port to listen on")
    args = parser.parse_args(argv)
    command = "simulate" if args.command == "seed" else args.command

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    if command == "fake-llm":
        return _fake_llm(args.port)

    settings = Settings()
    log = logging.getLogger(__name__)

    if command in ("migrate", "load-mock"):
        with psycopg.connect(settings.dsn, autocommit=True) as conn:
            repository.migrate(conn)
            if command == "load-mock":
                batch = f"mock-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
                load_scenarios(conn, _store(settings), batch_id=batch)
                log.info("serving tables loaded from scenarios (batch %s)", batch)
        return 0

    with ConnectionPool(settings.dsn, min_size=1, max_size=6, kwargs={"autocommit": True}) as pool:
        source = PgDataSource(pool) if settings.data_source == "pg" else _store(settings)
        handlers = build_handlers(Deps(source=source, model=model_from(settings)))
        log.info("data source: %s", settings.data_source)

        if command == "simulate":
            with pool.connection() as conn:
                created, total = service.simulate_pipeline(conn, source, handlers)
            log.info("pipeline: %d new alert tasks (%d flagged nights)", created, total)
            return 0

        if command == "web":
            import uvicorn

            from .web.app import create_app

            uvicorn.run(create_app(pool, handlers, source, settings), host=settings.web_host, port=settings.web_port)
            return 0

        worker = Worker(pool, handlers, LogNotifier(), settings)
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
    """OpenAI-compatible stand-in for the model, for running the worker without Ollama."""
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
