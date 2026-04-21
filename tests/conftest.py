"""
Shared fixtures for integration tests.

Provides a session-scoped temporary palace with real ChromaDB + SQLite,
and per-test singleton resets to prevent state leakage.
"""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import core.registry as _reg_module
from core.palace import configure
import core.palace as _palace_module


@pytest.fixture(scope="session")
def tmp_palace():
    """
    Create an isolated palace in a temp directory for the whole test session.

    Patches core.registry module-level paths so register_project() and
    configure() write to the temp dir instead of ~/.pneuma.
    """
    tmpdir = tempfile.mkdtemp(prefix="pneuma-test-")
    pneuma_home = Path(tmpdir) / "pneuma_home"
    pneuma_home.mkdir()

    project_dir = Path(tmpdir) / "fake-project"
    project_dir.mkdir()

    # Patch registry module-level constants
    with (
        patch.object(_reg_module, "PNEUMA_HOME", pneuma_home),
        patch.object(_reg_module, "REGISTRY_FILE", pneuma_home / "registry.json"),
        patch.object(_reg_module, "PALACES_DIR", pneuma_home / "palaces"),
    ):
        from core.registry import register_project

        proj = register_project(str(project_dir))
        configure(str(project_dir))

        yield {
            "tmpdir": tmpdir,
            "project_dir": str(project_dir),
            "project": proj,
        }

    # Cleanup
    _palace_module._config = None
    _palace_module._stack = None
    _palace_module._kg = None
    _palace_module._active_project = None
    os.environ.pop("MEMPALACE_PALACE_PATH", None)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_palace_singletons(request):
    """
    Reset palace singletons after every test so ChromaDB/KG state
    from one test doesn't leak into another.

    Only runs for tests that explicitly request the ``tmp_palace`` fixture.
    """
    if "tmp_palace" not in request.fixturenames:
        yield
        return

    tmp_palace = request.getfixturevalue("tmp_palace")
    yield

    # Re-configure to reset singletons with the same project
    with (
        patch.object(_reg_module, "PNEUMA_HOME", Path(tmp_palace["tmpdir"]) / "pneuma_home"),
        patch.object(_reg_module, "REGISTRY_FILE", Path(tmp_palace["tmpdir"]) / "pneuma_home" / "registry.json"),
        patch.object(_reg_module, "PALACES_DIR", Path(tmp_palace["tmpdir"]) / "pneuma_home" / "palaces"),
    ):
        configure(tmp_palace["project_dir"])
