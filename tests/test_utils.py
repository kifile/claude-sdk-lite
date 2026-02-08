"""Tests for utility functions."""

from unittest.mock import patch

import pytest

from claude_sdk_lite.executors import AsyncProcessExecutor, SyncProcessExecutor
from claude_sdk_lite.utils import find_tool_in_system, find_tool_in_system_sync


class AsyncIteratorMock:
    """Mock async iterator for testing."""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


class TestFindToolSync:
    """Test synchronous find_tool_in_system_sync function."""

    def test_find_tool_on_unix(self):
        """Test finding tool on Unix-like systems."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(SyncProcessExecutor, "execute") as mock_exec:
                mock_exec.return_value = iter([b"/usr/bin/claude\n"])
                result = find_tool_in_system_sync("claude")
                assert result == "/usr/bin/claude"

    def test_find_tool_on_windows_exe(self):
        """Test finding tool on Windows with .exe extension."""
        with patch("platform.system", return_value="Windows"):
            with patch.object(SyncProcessExecutor, "execute") as mock_exec:
                mock_exec.return_value = iter(
                    [
                        b"C:\\Program Files\\claude.exe\n",
                        b"C:\\Users\\user\\AppData\\Local\\claude.cmd\n",
                    ]
                )
                result = find_tool_in_system_sync("claude")
                assert result == "C:\\Program Files\\claude.exe"

    def test_find_tool_on_windows_cmd_only(self):
        """Test finding tool on Windows with only .cmd available."""
        with patch("platform.system", return_value="Windows"):
            with patch.object(SyncProcessExecutor, "execute") as mock_exec:
                mock_exec.return_value = iter([b"C:\\Users\\user\\AppData\\Local\\claude.cmd\n"])
                result = find_tool_in_system_sync("claude")
                assert result == "C:\\Users\\user\\AppData\\Local\\claude.cmd"

    def test_find_tool_on_windows_no_extension(self):
        """Test finding tool on Windows when path has no extension (Unix-style script)."""
        with patch("platform.system", return_value="Windows"):
            with patch.object(SyncProcessExecutor, "execute") as mock_exec:
                mock_exec.return_value = iter([b"/usr/local/bin/claude\n"])
                result = find_tool_in_system_sync("claude")
                assert result == "/usr/local/bin/claude"

    def test_find_tool_on_windows_batch(self):
        """Test finding tool on Windows with .bat extension."""
        with patch("platform.system", return_value="Windows"):
            with patch.object(SyncProcessExecutor, "execute") as mock_exec:
                mock_exec.return_value = iter([b"C:\\tools\\claude.bat\n"])
                result = find_tool_in_system_sync("claude")
                assert result == "C:\\tools\\claude.bat"

    def test_find_tool_on_windows_prefers_exe_over_cmd(self):
        """Test that Windows prefers .exe over .cmd when both exist."""
        with patch("platform.system", return_value="Windows"):
            with patch.object(SyncProcessExecutor, "execute") as mock_exec:
                mock_exec.return_value = iter(
                    [
                        b"C:\\Users\\user\\AppData\\Local\\claude.cmd\n",
                        b"C:\\Program Files\\claude.exe\n",
                    ]
                )
                result = find_tool_in_system_sync("claude")
                assert result == "C:\\Program Files\\claude.exe"

    def test_find_tool_not_found(self):
        """Test when tool is not found."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(SyncProcessExecutor, "execute") as mock_exec:
                mock_exec.return_value = iter([])
                result = find_tool_in_system_sync("claude")
                assert result is None

    def test_find_tool_multiple_paths_unix_returns_first(self):
        """Test that Unix returns first path when multiple found."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(SyncProcessExecutor, "execute") as mock_exec:
                mock_exec.return_value = iter([b"/usr/local/bin/claude\n", b"/usr/bin/claude\n"])
                result = find_tool_in_system_sync("claude")
                assert result == "/usr/local/bin/claude"

    def test_find_tool_handles_runtime_error(self):
        """Test error handling when executor raises RuntimeError."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(
                SyncProcessExecutor, "execute", side_effect=RuntimeError("Command failed")
            ):
                result = find_tool_in_system_sync("claude")
                assert result is None

    def test_find_tool_handles_os_error(self):
        """Test error handling when OSError occurs."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(
                SyncProcessExecutor, "execute", side_effect=OSError("Tool not found")
            ):
                result = find_tool_in_system_sync("claude")
                assert result is None

    def test_find_tool_handles_empty_line_at_end(self):
        """Test handling of trailing empty line in output."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(SyncProcessExecutor, "execute") as mock_exec:
                # Simulate output with trailing empty line
                mock_exec.return_value = iter([b"/usr/bin/claude\n", b"\n"])
                result = find_tool_in_system_sync("claude")
                assert result == "/usr/bin/claude"

    def test_find_tool_handles_multiple_empty_lines(self):
        """Test handling of multiple empty lines in output."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(SyncProcessExecutor, "execute") as mock_exec:
                mock_exec.return_value = iter([b"/usr/bin/claude\n", b"\n", b"\n"])
                result = find_tool_in_system_sync("claude")
                assert result == "/usr/bin/claude"


@pytest.mark.asyncio
class TestFindToolAsync:
    """Test asynchronous find_tool_in_system function."""

    async def test_find_tool_on_unix(self):
        """Test finding tool on Unix-like systems."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(AsyncProcessExecutor, "async_execute") as mock_exec:
                mock_exec.return_value = AsyncIteratorMock([b"/usr/bin/claude\n"])
                result = await find_tool_in_system("claude")
                assert result == "/usr/bin/claude"

    async def test_find_tool_on_windows_exe(self):
        """Test finding tool on Windows with .exe extension."""
        with patch("platform.system", return_value="Windows"):
            with patch.object(AsyncProcessExecutor, "async_execute") as mock_exec:
                mock_exec.return_value = AsyncIteratorMock(
                    [
                        b"C:\\Program Files\\claude.exe\n",
                        b"C:\\Users\\user\\AppData\\Local\\claude.cmd\n",
                    ]
                )
                result = await find_tool_in_system("claude")
                assert result == "C:\\Program Files\\claude.exe"

    async def test_find_tool_on_windows_no_extension(self):
        """Test finding tool on Windows when path has no extension (Unix-style script)."""
        with patch("platform.system", return_value="Windows"):
            with patch.object(AsyncProcessExecutor, "async_execute") as mock_exec:
                mock_exec.return_value = AsyncIteratorMock([b"/usr/local/bin/claude\n"])
                result = await find_tool_in_system("claude")
                assert result == "/usr/local/bin/claude"

    async def test_find_tool_on_windows_batch(self):
        """Test finding tool on Windows with .bat extension."""
        with patch("platform.system", return_value="Windows"):
            with patch.object(AsyncProcessExecutor, "async_execute") as mock_exec:
                mock_exec.return_value = AsyncIteratorMock([b"C:\\tools\\claude.bat\n"])
                result = await find_tool_in_system("claude")
                assert result == "C:\\tools\\claude.bat"

    async def test_find_tool_not_found(self):
        """Test when tool is not found."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(AsyncProcessExecutor, "async_execute") as mock_exec:
                mock_exec.return_value = AsyncIteratorMock([])
                result = await find_tool_in_system("claude")
                assert result is None

    async def test_find_tool_handles_runtime_error(self):
        """Test error handling when executor raises RuntimeError."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(
                AsyncProcessExecutor, "async_execute", side_effect=RuntimeError("Command failed")
            ):
                result = await find_tool_in_system("claude")
                assert result is None

    async def test_find_tool_handles_os_error(self):
        """Test error handling when OSError occurs."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(
                AsyncProcessExecutor, "async_execute", side_effect=OSError("Tool not found")
            ):
                result = await find_tool_in_system("claude")
                assert result is None

    async def test_find_tool_handles_empty_line_at_end(self):
        """Test handling of trailing empty line in output."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(AsyncProcessExecutor, "async_execute") as mock_exec:
                # Simulate output with trailing empty line
                mock_exec.return_value = AsyncIteratorMock([b"/usr/bin/claude\n", b"\n"])
                result = await find_tool_in_system("claude")
                assert result == "/usr/bin/claude"

    async def test_find_tool_handles_multiple_empty_lines(self):
        """Test handling of multiple empty lines in output."""
        with patch("platform.system", return_value="Linux"):
            with patch.object(AsyncProcessExecutor, "async_execute") as mock_exec:
                mock_exec.return_value = AsyncIteratorMock([b"/usr/bin/claude\n", b"\n", b"\n"])
                result = await find_tool_in_system("claude")
                assert result == "/usr/bin/claude"
