"""Tests for ProcessCollector.

Relates-to: FR-2
"""

from unittest.mock import MagicMock, patch

import psutil

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
