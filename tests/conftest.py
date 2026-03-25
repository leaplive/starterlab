"""Shared fixtures for starterlab tests."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from leap.core import auth, storage
from leap.main import create_app

STARTERLAB_ROOT = Path(__file__).resolve().parent.parent
TEST_PASSWORD = "benchtest"


@pytest.fixture(scope="module")
def starterlab_root(tmp_path_factory):
    """Copy starterlab into a temp directory with test credentials.

    Uses module scope so the app is created once per test file.
    """
    tmp = tmp_path_factory.mktemp("starterlab")

    # Copy experiments and assets
    shutil.copytree(STARTERLAB_ROOT / "experiments", tmp / "experiments")
    if (STARTERLAB_ROOT / "assets").exists():
        shutil.copytree(STARTERLAB_ROOT / "assets", tmp / "assets")

    # Copy README.md (lab metadata)
    shutil.copy2(STARTERLAB_ROOT / "README.md", tmp / "README.md")

    # Create test admin credentials
    config_dir = tmp / "config"
    config_dir.mkdir()
    cred = auth.hash_password(TEST_PASSWORD)
    with open(config_dir / "admin_credentials.json", "w") as f:
        json.dump(cred, f)

    yield tmp

    storage.close_all_engines()
