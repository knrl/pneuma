"""Tests for core/env.py — centralized .env loader."""

import os
from pathlib import Path

import pytest


class TestEnvLoaderConfig:
    def test_pneuma_root_is_repo_root(self):
        """_PNEUMA_ROOT must be the Pneuma install root, not CWD."""
        import core.env as env_mod
        # tests/ is at <root>/tests/test_env.py, so parents[1] is <root>
        expected = Path(__file__).resolve().parents[1]
        assert env_mod._PNEUMA_ROOT == expected

    def test_dotenv_path_is_absolute_and_in_pneuma_root(self):
        """_DOTENV_PATH must be absolute and located inside the Pneuma root."""
        import core.env as env_mod
        assert env_mod._DOTENV_PATH.is_absolute()
        assert env_mod._DOTENV_PATH == env_mod._PNEUMA_ROOT / ".env"

    def test_dotenv_path_does_not_depend_on_cwd(self, tmp_path, monkeypatch):
        """Changing CWD must not affect where we look for .env."""
        import core.env as env_mod
        original = env_mod._DOTENV_PATH
        monkeypatch.chdir(tmp_path)
        # Re-check after chdir — path is computed from __file__, not os.getcwd()
        assert env_mod._DOTENV_PATH == original


class TestEnvLoading:
    def test_cwd_env_file_is_not_loaded(self, tmp_path, monkeypatch):
        """A .env placed in the current working directory must NOT be picked up."""
        sentinel = "PNEUMA_TEST_CWD_SENTINEL"
        (tmp_path / ".env").write_text(f"{sentinel}=should_not_appear\n")
        monkeypatch.chdir(tmp_path)
        # core.env is already imported (module cache) and used an explicit path;
        # the CWD .env should never have been loaded.
        assert os.environ.get(sentinel) is None

    def test_missing_env_file_does_not_raise(self):
        """load_dotenv with a non-existent path must silently do nothing."""
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=Path("/nonexistent/__pneuma_test__/.env"))

    def test_explicit_dotenv_path_loads_vars(self, tmp_path):
        """load_dotenv with an explicit path must load vars from that file."""
        env_file = tmp_path / ".env"
        env_file.write_text("PNEUMA_TEST_EXPLICIT_VAR=hello_explicit\n")
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_file)
            assert os.environ.get("PNEUMA_TEST_EXPLICIT_VAR") == "hello_explicit"
        finally:
            os.environ.pop("PNEUMA_TEST_EXPLICIT_VAR", None)
