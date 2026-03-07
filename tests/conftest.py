"""Shared pytest configuration and fixtures."""

from __future__ import annotations

import os

import pytest

# Auto-skip tests marked @pytest.mark.network when running in CI
_IN_CI = os.environ.get("CI", "").lower() in ("true", "1", "yes")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "network: requires real network targets (skipped in CI)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not _IN_CI:
        return
    skip_network = pytest.mark.skip(reason="network tests skipped in CI")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)
