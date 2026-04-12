"""Pytest configuration for Bug Bible regression tests."""

import os

import pytest


def pytest_addoption(parser):
    """Add --pack-dir CLI option for the custom node pack path."""
    parser.addoption(
        "--pack-dir",
        action="store",
        default=".",
        help="Path to the ComfyUI custom node pack to test",
    )
