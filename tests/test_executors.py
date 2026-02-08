"""Tests for process executors."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_sdk_lite.executors import AsyncProcessExecutor, SyncProcessExecutor


class MockStdout:
    """Mock stdout for testing."""

    def __init__(self, lines):
        self.lines = lines
        self.index = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.index >= len(self.lines):
            raise StopIteration
        line = self.lines[self.index]
        self.index += 1
        return line.encode() if isinstance(line, str) else line


class MockSyncProcess:
    """Mock subprocess.Popen object for testing."""

    def __init__(self, stdout_lines=None, returncode=0, stderr=b""):
        self.stdout_lines = stdout_lines or []
        self.returncode = returncode
        self.stderr_data = stderr
        self._stdout_index = 0

        # Create mock stdout
        self.stdout = MockStdout(self.stdout_lines)

        # Create mock stderr
        self.stderr = MagicMock()
        self.stderr.read = MagicMock(return_value=self.stderr_data)

    def poll(self):
        """Check if process has terminated."""
        return None if self._stdout_index < len(self.stdout_lines) else self.returncode

    def wait(self, timeout=None):
        """Wait for process to complete."""
        self._stdout_index = len(self.stdout_lines)
        return self.returncode

    def terminate(self):
        """Terminate the process."""
        self._stdout_index = len(self.stdout_lines)

    def kill(self):
        """Kill the process."""
        self._stdout_index = len(self.stdout_lines)


class AsyncMockStdout:
    """Mock async stdout."""

    def __init__(self, lines):
        self.lines = lines
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.lines):
            raise StopAsyncIteration
        line = self.lines[self.index]
        self.index += 1
        return line.encode() if isinstance(line, str) else line


class AsyncMockProcess:
    """Mock async subprocess for testing."""

    def __init__(self, stdout_lines=None, returncode=0, stderr=b""):
        self.stdout_lines = stdout_lines or []
        self.returncode = returncode
        self.stderr_data = stderr
        self.stdout = AsyncMockStdout(self.stdout_lines)
        self.stderr = MagicMock()
        self.stderr.read = AsyncMock(return_value=self.stderr_data)

    async def wait(self):
        return self.returncode


@pytest.fixture
def mock_find_cli():
    """Mock CLI finding to avoid actual subprocess calls."""
    with patch("claude_sdk_lite.utils.find_tool_in_system_sync", return_value="/usr/bin/claude"):
        yield


@pytest.mark.asyncio
class TestAsyncProcessExecutor:
    """Test AsyncProcessExecutor."""

    async def test_async_execute_yields_raw_lines(self):
        """Test that async_execute yields raw line bytes."""
        executor = AsyncProcessExecutor()

        lines = ["line1", "line2", "line3"]
        mock_process = AsyncMockProcess(stdout_lines=lines, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result_lines = []
            async for line in executor.async_execute(["echo", "test"]):
                result_lines.append(line.decode())

            assert result_lines == ["line1", "line2", "line3"]

    async def test_async_execute_handles_cli_errors(self):
        """Test that async_execute handles CLI errors."""
        executor = AsyncProcessExecutor()

        mock_process = AsyncMockProcess(returncode=1)
        mock_process.stderr = MagicMock()
        mock_process.stderr.read = AsyncMock(return_value=b"Error: Test error\n")

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(RuntimeError) as exc_info:
                async for _ in executor.async_execute(["false"]):
                    pass

            assert exc_info.value.message == "CLI exited with code 1"
            assert exc_info.value.exit_code == 1
            assert exc_info.value.stderr == "Error: Test error\n"

    async def test_async_stdout_pipe_missing_raises_error(self):
        """Test error when async stdout pipe cannot be created."""
        executor = AsyncProcessExecutor()

        mock_process = AsyncMock()
        mock_process.stdout = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(RuntimeError, match="Failed to create subprocess stdout pipe"):
                async for _ in executor.async_execute(["echo", "test"]):
                    pass


class TestSyncProcessExecutor:
    """Test SyncProcessExecutor."""

    def test_execute_yields_raw_lines(self, mock_find_cli):
        """Test that execute yields raw line bytes."""
        executor = SyncProcessExecutor()

        lines = ["line1", "line2", "line3"]
        mock_process = MockSyncProcess(stdout_lines=lines, returncode=0)

        with patch("subprocess.Popen", return_value=mock_process):
            result_lines = []
            for line in executor.execute(["echo", "test"]):
                result_lines.append(line.decode())

            assert result_lines == ["line1", "line2", "line3"]

    def test_execute_handles_cli_errors(self, mock_find_cli):
        """Test that execute handles CLI errors."""
        executor = SyncProcessExecutor()

        mock_process = MockSyncProcess(stdout_lines=[], returncode=1, stderr=b"Error: Test error\n")

        with patch("subprocess.Popen", return_value=mock_process):
            with pytest.raises(RuntimeError) as exc_info:
                for _ in executor.execute(["false"]):
                    pass

            assert exc_info.value.message == "CLI exited with code 1"
            assert exc_info.value.exit_code == 1
            assert exc_info.value.stderr == "Error: Test error\n"

    def test_cleanup_process_terminated_successfully(self, mock_find_cli):
        """Test cleanup when process terminates successfully."""
        executor = SyncProcessExecutor()

        mock_process = MockSyncProcess(stdout_lines=["done"])
        mock_process.wait = MagicMock(return_value=0)
        mock_process.terminate = MagicMock()
        mock_process.poll = lambda: 0  # Already terminated

        with patch("subprocess.Popen", return_value=mock_process):
            for _ in executor.execute(["echo", "done"]):
                pass

        # Verify terminate was NOT called (already terminated)
        mock_process.terminate.assert_not_called()

    def test_cleanup_process_needs_termination(self, mock_find_cli):
        """Test cleanup when process needs to be terminated."""
        executor = SyncProcessExecutor()

        mock_process = MockSyncProcess(stdout_lines=["line1", "line2"])
        mock_process.wait = MagicMock(return_value=0)
        mock_process.terminate = MagicMock()
        mock_process.poll = lambda: None  # Still running

        with patch("subprocess.Popen", return_value=mock_process):
            for _ in executor.execute(["echo", "test"]):
                pass

        # Verify terminate WAS called (process was still running)
        mock_process.terminate.assert_called_once()

    def test_stdout_pipe_missing_raises_error(self, mock_find_cli):
        """Test error when stdout pipe cannot be created."""
        executor = SyncProcessExecutor()

        mock_process = MagicMock()
        mock_process.stdout = None

        with patch("subprocess.Popen", return_value=mock_process):
            with pytest.raises(RuntimeError, match="Failed to create subprocess stdout pipe"):
                for _ in executor.execute(["echo", "test"]):
                    pass


@pytest.mark.asyncio
class TestExecutorIntegration:
    """Integration tests for executors with query functions."""

    async def test_sync_executor_via_query(self, mock_find_cli):
        """Test sync executor through query function."""
        import json

        from claude_sdk_lite import query

        responses = [
            {
                "type": "assistant",
                "message": {
                    "model": "sonnet",
                    "content": [{"type": "text", "text": "Test response"}],
                },
            }
        ]

        mock_process = MockSyncProcess(
            stdout_lines=[json.dumps(r) for r in responses], returncode=0
        )

        with patch("subprocess.Popen", return_value=mock_process):
            messages = []
            for msg in query(prompt="Test"):
                messages.append(msg)

            assert len(messages) == 1
            assert messages[0].content[0].text == "Test response"

    async def test_async_executor_via_async_query(self):
        """Test async executor through async_query function."""
        from claude_sdk_lite import async_query

        # Use JSON strings, not dict objects
        responses = [
            '{"type": "assistant", "message": {"model": "sonnet", "content": [{"type": "text", "text": "Test response"}]}}'
        ]

        mock_process = AsyncMockProcess(stdout_lines=responses, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = []
            async for msg in async_query(prompt="Test"):
                messages.append(msg)

            assert len(messages) == 1
            assert messages[0].content[0].text == "Test response"
