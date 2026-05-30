"""End-to-end CLI tests using typer.CliRunner.

Relates-to: FR-1
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from taskguard.cli.main import app

runner = CliRunner()


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Provide an isolated data directory for each test."""
    return tmp_path


class TestWatchCommand:
    def test_watch_file_happy(self, data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TASKGUARD_DATA_DIR", str(data_dir))
        result = runner.invoke(
            app, ["watch", "demo-bash", "--log", "file://C:\\test.log 127.0.0.1 -n 100"]
        )
        assert result.exit_code == 0, result.output

    def test_watch_file_with_pid(self, data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TASKGUARD_DATA_DIR", str(data_dir))
        result = runner.invoke(
            app, ["watch", "demo-pid", "--pid", "12345", "--log", "file://C:\\data\\dl.log"]
        )
        assert result.exit_code == 0, result.output

    def test_watch_duplicate_alias(self, data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TASKGUARD_DATA_DIR", str(data_dir))
        runner.invoke(app, ["watch", "dup", "--log", "file://C:\\test.log"])
        result = runner.invoke(app, ["watch", "dup", "--log", "file://C:\\test.log"])
        assert result.exit_code == 2
        assert "alias_exists" in result.output or "exists" in result.output

    def test_watch_missing_log(self, data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TASKGUARD_DATA_DIR", str(data_dir))
        result = runner.invoke(app, ["watch", "x"])
        assert result.exit_code != 0


class TestListCommand:
    def test_list_shows_registered(self, data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TASKGUARD_DATA_DIR", str(data_dir))
        runner.invoke(app, ["watch", "a", "--log", "file://C:\\test.log"])
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "a" in result.output


class TestStatusCommand:
    def test_status_found(self, data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TASKGUARD_DATA_DIR", str(data_dir))
        runner.invoke(app, ["watch", "a", "--log", "file://C:\\test.log"])
        result = runner.invoke(app, ["status", "a"])
        assert result.exit_code == 0
        assert "a" in result.output

    def test_status_not_found(self, data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TASKGUARD_DATA_DIR", str(data_dir))
        result = runner.invoke(app, ["status", "nonexistent"])
        assert result.exit_code == 3


class TestUnwatchCommand:
    def test_unwatch_happy(self, data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TASKGUARD_DATA_DIR", str(data_dir))
        runner.invoke(app, ["watch", "a", "--log", "file://C:\\test.log"])
        result = runner.invoke(app, ["unwatch", "a"])
        assert result.exit_code == 0, result.output

    def test_unwatch_after_unwatch_not_found(
        self, data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TASKGUARD_DATA_DIR", str(data_dir))
        runner.invoke(app, ["watch", "a", "--log", "file://C:\\test.log"])
        runner.invoke(app, ["unwatch", "a"])
        result = runner.invoke(app, ["status", "a"])
        assert result.exit_code == 3
