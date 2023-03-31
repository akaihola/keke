import pytest
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.python import Function


def pytest_configure(config: Config) -> None:
    config.addinivalue_line("markers", "network: mark test as requiring network access")


def pytest_addoption(parser: Parser) -> None:
    parser.addoption(
        "--network",
        action="store_true",
        help="Run tests that require network access",
    )


def pytest_collection_modifyitems(config: Config, items: list[Function]) -> None:
    if config.getoption("--network"):
        return
    skip_marker = pytest.mark.skip(reason="network tests are skipped by default")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_marker)
