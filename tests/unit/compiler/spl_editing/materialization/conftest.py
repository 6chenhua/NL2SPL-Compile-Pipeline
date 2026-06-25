"""Pytest configuration for materialization tests."""

import pytest

def pytest_configure(config):
    # Register the custom marker to prevent pytest warnings
    config.addinivalue_line(
        "markers", "contract_pending: mark test as pending contract implementation"
    )

def pytest_addoption(parser):
    parser.addoption(
        "--run-pending",
        action="store_true",
        default=False,
        help="run contract pending tests",
    )

def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-pending"):
        return
    
    selected = []
    deselected = []
    for item in items:
        if item.get_closest_marker("contract_pending"):
            deselected.append(item)
        else:
            selected.append(item)
    
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
