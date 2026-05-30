"""Tests for find_process tool.

Relates-to: FR-4
"""

from unittest.mock import MagicMock, patch

import pytest

from taskguard.tools.find_process import FindProcessTool, _find_processes_sync


class TestFindProcessSync:
    def test_empty_name(self) -> None:
        """Empty query matches nothing."""
        with patch("taskguard.tools.find_process.psutil.process_iter", return_value=iter([])):
            result = _find_processes_sync("")
        assert result == []

    def test_exact_name_match(self) -> None:
        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 1234,
            "name": "wget.exe",
            "cmdline": ["wget.exe", "-O", "file.zip"],
        }
        with patch(
            "taskguard.tools.find_process.psutil.process_iter", return_value=iter([mock_proc])
        ):
            result = _find_processes_sync("wget")
        assert len(result) == 1
        assert result[0]["pid"] == 1234
        assert result[0]["name"] == "wget.exe"

    def test_cmdline_match(self) -> None:
        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 5678,
            "name": "python.exe",
            "cmdline": ["python.exe", "download.py"],
        }
        with patch(
            "taskguard.tools.find_process.psutil.process_iter", return_value=iter([mock_proc])
        ):
            result = _find_processes_sync("download")
        assert len(result) == 1
        assert result[0]["pid"] == 5678

    def test_case_insensitive(self) -> None:
        mock_proc = MagicMock()
        mock_proc.info = {"pid": 1111, "name": "WGET.EXE", "cmdline": ["WGET.EXE"]}
        with patch(
            "taskguard.tools.find_process.psutil.process_iter", return_value=iter([mock_proc])
        ):
            result = _find_processes_sync("wget")
        assert len(result) == 1

    def test_sort_order_exact_first(self) -> None:
        """Exact name match should be sorted before cmdline match."""
        mock_p1 = MagicMock()
        mock_p1.info = {"pid": 1, "name": "python.exe", "cmdline": ["python.exe", "mydownload.py"]}
        mock_p2 = MagicMock()
        mock_p2.info = {"pid": 2, "name": "download.exe", "cmdline": ["download.exe"]}
        with patch(
            "taskguard.tools.find_process.psutil.process_iter",
            return_value=iter([mock_p1, mock_p2]),
        ):
            result = _find_processes_sync("download")
        assert len(result) == 2
        assert result[0]["pid"] == 2  # exact match first
        assert result[1]["pid"] == 1

    def test_access_denied_skipped(self) -> None:
        from unittest.mock import PropertyMock

        import psutil

        mock_proc = MagicMock()
        type(mock_proc).info = PropertyMock(side_effect=psutil.AccessDenied("denied"))
        with patch(
            "taskguard.tools.find_process.psutil.process_iter", return_value=iter([mock_proc])
        ):
            result = _find_processes_sync("secret")
        assert result == []

    def test_no_such_process_skipped(self) -> None:
        from unittest.mock import PropertyMock

        import psutil

        mock_proc = MagicMock()
        type(mock_proc).info = PropertyMock(side_effect=psutil.NoSuchProcess(1))
        with patch(
            "taskguard.tools.find_process.psutil.process_iter", return_value=iter([mock_proc])
        ):
            result = _find_processes_sync("gone")
        assert result == []


class TestFindProcessTool:
    @pytest.mark.asyncio
    async def test_empty_name(self) -> None:
        tool = FindProcessTool()
        result = await tool.execute({"name": "  "})
        assert result.ok is False
        assert result.error_code == "empty_name"

    @pytest.mark.asyncio
    async def test_no_match(self) -> None:
        tool = FindProcessTool()
        with patch("taskguard.tools.find_process.psutil.process_iter", return_value=iter([])):
            result = await tool.execute({"name": "nonexistent"})
        assert result.ok is True
        assert result.data == []

    @pytest.mark.asyncio
    async def test_single_match(self) -> None:
        tool = FindProcessTool()
        mock_proc = MagicMock()
        mock_proc.info = {"pid": 1234, "name": "wget.exe", "cmdline": ["wget.exe"]}
        with patch(
            "taskguard.tools.find_process.psutil.process_iter", return_value=iter([mock_proc])
        ):
            result = await tool.execute({"name": "wget"})
        assert result.ok is True
        assert len(result.data) == 1
        assert result.data[0]["pid"] == 1234

    @pytest.mark.asyncio
    async def test_multiple_matches(self) -> None:
        tool = FindProcessTool()
        mock_p1 = MagicMock()
        mock_p1.info = {"pid": 1111, "name": "wget.exe", "cmdline": ["wget.exe", "-O", "a.zip"]}
        mock_p2 = MagicMock()
        mock_p2.info = {"pid": 2222, "name": "wget.exe", "cmdline": ["wget.exe", "-O", "b.zip"]}
        with patch(
            "taskguard.tools.find_process.psutil.process_iter",
            return_value=iter([mock_p1, mock_p2]),
        ):
            result = await tool.execute({"name": "wget"})
        assert result.ok is True
        assert len(result.data) == 2
