import argparse
import logging
import signal
import sys
import threading

import psycopg
from psycopg_pool import ConnectionPool

from . import repository
from .notify import LogNotifier
from .settings import Settings
from .stages import default_stages
from .worker import Worker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llm_worker")
    parser.add_argument("command", choices=["migrate", "seed", "run", "once"])
    command = parser.parse_args(argv).command

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    settings = Settings()

    if command in ("migrate", "seed"):
        with psycopg.connect(settings.dsn, autocommit=True) as conn:
            repository.migrate(conn)
            if command == "seed":
                repository.seed(conn)
        return 0

    with ConnectionPool(settings.dsn, min_size=1, max_size=2, kwargs={"autocommit": True}) as pool:
        worker = Worker(pool, default_stages(settings), LogNotifier(), settings)
        if command == "once":
            while worker.run_once():
                pass
            return 0

        stop = threading.Event()
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: stop.set())
        worker.run(stop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
