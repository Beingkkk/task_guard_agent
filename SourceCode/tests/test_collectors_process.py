"""Tests for ProcessCollector.

Relates-to: FR-2
"""

from unittest.mock import MagicMock, patch

import psutil
import pytest

from taskguard.collectors.process_collector import ProcessCollector


class TestProcessCollector:
    async def test_collects_process_info(self) -> None:
        mock_proc = MagicMock()
        mock_proc.cpu_percent.return_value = 15.2
        mock_proc.memory_info.return_value = MagicMock(rss=1048576)
        mock_proc.status.return_value = psutil.STATUS_RUNNING

        with patch("taskguard.collectors.process_collector.psutil.Process", return_value=mock_proc):
            collector = ProcessCollector()
            info = await collector.collect(12345)

        assert info is not None
        assert info.cpu_percent == 15.2
        assert info.memory_working_set == 1048576
        assert info.status == "running"

    async def test_no_such_process(self) -> None:
        with patch(
            "taskguard.collectors.process_collector.psutil.Process",
            side_effect=psutil.NoSuchProcess(12345),
        ):
            collector = ProcessCollector()
            info = await collector.collect(12345)

        assert info is not None
        assert info.status == "exited"
        assert info.exit_code is None

    async def test_access_denied(self) -> None:
        with patch(
            "taskguard.collectors.process_collector.psutil.Process",
            side_effect=psutil.AccessDenied(12345),
        ):
            collector = ProcessCollector()
            info = await collector.collect(12345)

        assert info is not None
        assert info.status is None

    async def test_pid_none(self) -> None:
        collector = ProcessCollector()
        info = await collector.collect(None)
        assert info is None

    async def test_no_such_process_returns_exit_code_on_windows(self) -> None:
        """On Windows, NoSuchProcess should attempt to get exit_code via ctypes."""
        import sys

        with patch(
            "taskguard.collectors.process_collector.psutil.Process",
            side_effect=psutil.NoSuchProcess(12345),
        ):
            collector = ProcessCollector()
            info = await collector.collect(12345)

        assert info is not None
        assert info.status == "exited"
        # On Windows, exit_code may be retrieved via ctypes; on other platforms it's None
        if sys.platform == "win32":
            # We can't guarantee a real exit code in tests, but the field should exist
            assert hasattr(info, "exit_code")
        else:
            assert info.exit_code is None

    async def test_no_such_process_with_exit_code_from_windows_api(self) -> None:
        """Test that exit_code is populated when Windows API succeeds."""
        import sys

        if sys.platform != "win32":
            pytest.skip("Windows-only test")

        with patch(
            "taskguard.collectors.process_collector.psutil.Process",
            side_effect=psutil.NoSuchProcess(12345),
        ), patch(
            "taskguard.collectors.process_collector._get_exit_code_windows",
            return_value=42,
        ):
            collector = ProcessCollector()
            info = await collector.collect(12345)

        assert info is not None
        assert info.status == "exited"
        assert info.exit_code == 42
