from pathlib import Path

import pytest

pytest_plugins = (
    "tests.fixtures.db",
    "tests.fixtures.influx",
    "tests.fixtures.app",
    "tests.fixtures.factories",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-perf",
        action="store_true",
        default=False,
        help="run manual telemetry performance benchmarks under tests/perf",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Apply default markers by folder to keep marker usage consistent."""
    run_perf = config.getoption("--run-perf")
    skip_perf = pytest.mark.skip(reason="performance benchmarks are manual; use --run-perf to include them")

    for item in items:
        parts = Path(item.path).parts
        if "tests" not in parts:
            continue
        scope_idx = parts.index("tests") + 1
        scope = parts[scope_idx] if scope_idx < len(parts) else None

        if scope == "integration":
            item.add_marker(pytest.mark.integration)
        elif scope == "smoke":
            item.add_marker(pytest.mark.smoke)
        elif scope == "unit":
            item.add_marker(pytest.mark.unit)
        elif scope == "perf":
            item.add_marker(pytest.mark.perf)
            if not run_perf:
                item.add_marker(skip_perf)
