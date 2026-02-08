"""Tests for process executors using real subprocess calls."""

import json
import platform

import pytest

from claude_sdk_lite.executors import AsyncProcessExecutor, SyncProcessExecutor

# ========== Platform Detection ==========
IS_WINDOWS = platform.system() == "Windows"


# ========== Helper Functions ==========


def get_shell_command():
    """Get appropriate shell command for the platform."""
    return ["cmd.exe", "/c"] if IS_WINDOWS else ["sh", "-c"]


def get_false_command():
    """Get a command that always exits with code 1."""
    return ["cmd.exe", "/c", "exit 1"] if IS_WINDOWS else ["false"]


def create_json_command(json_lines):
    """Create a shell command that outputs JSON lines."""
    # Use printf to preserve JSON formatting (especially quotes)
    lines_str = "\\n".join(json_lines)
    if IS_WINDOWS:
        return ["cmd.exe", "/c", f'printf "{lines_str}\\n"']
    else:
        return ["sh", "-c", f"printf '{lines_str}\\n'"]


def create_error_command(exit_code, stderr_message=""):
    """Create a command that exits with custom error code."""
    if IS_WINDOWS:
        if stderr_message:
            return ["cmd.exe", "/c", f"echo {stderr_message} >&2 & exit {exit_code}"]
        return ["cmd.exe", "/c", f"exit {exit_code}"]
    else:
        if stderr_message:
            return ["sh", "-c", f"echo '{stderr_message}' >&2; exit {exit_code}"]
        return ["sh", "-c", f"exit {exit_code}"]


# ========== SyncProcessExecutor Tests ==========


class TestSyncProcessExecutor:
    """Test SyncProcessExecutor with real subprocess calls."""

    def test_execute_echo_command(self):
        """Test executing simple echo command."""
        executor = SyncProcessExecutor()
        result = list(executor.execute(["echo", "hello", "world"]))
        assert len(result) == 1
        assert result[0].decode() == "hello world\n"

    def test_execute_multi_line_output(self):
        """Test executing command that produces multiple lines."""
        executor = SyncProcessExecutor()
        result = list(executor.execute(["seq", "1", "5"]))
        assert len(result) == 5
        assert [line.strip().decode() for line in result] == ["1", "2", "3", "4", "5"]

    def test_execute_json_output(self):
        """Test executing command with JSON output."""
        executor = SyncProcessExecutor()
        json_lines = [
            '{"type": "test", "id": 1}',
            '{"type": "test", "id": 2}',
            '{"type": "test", "id": 3}',
        ]

        cmd = create_json_command(json_lines)
        result = list(executor.execute(cmd))
        assert len(result) == 3
        assert json.loads(result[0].decode())["id"] == 1
        assert json.loads(result[1].decode())["id"] == 2
        assert json.loads(result[2].decode())["id"] == 3

    def test_execute_command_with_error(self):
        """Test executing command that exits with non-zero code."""
        executor = SyncProcessExecutor()

        cmd = get_false_command()
        with pytest.raises(RuntimeError) as exc_info:
            list(executor.execute(cmd))

        assert exc_info.value.message == "CLI exited with code 1"
        assert exc_info.value.exit_code == 1

    def test_execute_command_with_custom_error(self):
        """Test executing command with custom error code."""
        executor = SyncProcessExecutor()

        cmd = create_error_command(42, "Custom error message")
        with pytest.raises(RuntimeError) as exc_info:
            list(executor.execute(cmd))

        assert exc_info.value.exit_code == 42
        assert "Custom error" in exc_info.value.stderr or "error" in exc_info.value.stderr.lower()

    def test_execute_cat_with_stdin(self):
        """Test executing cat that reads from stdin (if supported)."""
        executor = SyncProcessExecutor()
        # cat with no arguments just waits for stdin
        # This should produce output only if we provide input
        # Since we don't provide input, it will just exit
        result = list(executor.execute(["cat"]))
        # cat with no input will exit immediately
        assert len(result) == 0

    def test_execute_grep_command(self):
        """Test executing grep with pattern that has matches."""
        executor = SyncProcessExecutor()
        # grep with -E and pattern, using echo to provide input
        result = list(executor.execute(["sh", "-c", "echo test | grep -E '^test$'"]))
        assert len(result) == 1
        assert result[0].decode().strip() == "test"

    def test_execute_with_large_output(self):
        """Test executing command that produces large output."""
        executor = SyncProcessExecutor()
        # Generate 1000 lines
        result = list(executor.execute(["seq", "1", "1000"]))
        assert len(result) == 1000
        assert result[0].decode().strip() == "1"
        assert result[-1].decode().strip() == "1000"

    def test_execute_with_unicode_output(self):
        """Test executing command that produces Unicode output."""
        executor = SyncProcessExecutor()

        # Use echo with Unicode text directly
        messages = ["Hello 世界", "Emoji 🎉", "Привет мир"]
        cmd = get_shell_command() + [f'echo "{messages[0]}\\n{messages[1]}\\n{messages[2]}"']

        result = list(executor.execute(cmd))
        # Result may be split differently depending on platform
        combined_output = b"".join(result).decode()
        assert "世界" in combined_output or "世界" in result[0].decode()
        assert "🎉" in combined_output
        assert "Привет" in combined_output


# ========== AsyncProcessExecutor Tests ==========


class TestAsyncProcessExecutor:
    """Test AsyncProcessExecutor with real subprocess calls."""

    @pytest.mark.asyncio
    async def test_async_execute_echo_command(self):
        """Test async executing simple echo command."""
        executor = AsyncProcessExecutor()
        result = []
        async for line in executor.async_execute(["echo", "async", "test"]):
            result.append(line)

        assert len(result) == 1
        assert result[0].decode() == "async test\n"

    @pytest.mark.asyncio
    async def test_async_execute_multi_line_output(self):
        """Test async executing command with multiple lines."""
        executor = AsyncProcessExecutor()
        result = []
        async for line in executor.async_execute(["seq", "1", "5"]):
            result.append(line)

        assert len(result) == 5
        assert [line.strip().decode() for line in result] == ["1", "2", "3", "4", "5"]

    @pytest.mark.asyncio
    async def test_async_execute_json_output(self):
        """Test async executing command with JSON output."""
        executor = AsyncProcessExecutor()
        json_lines = ['{"type": "async", "id": 1}', '{"type": "async", "id": 2}']

        cmd = create_json_command(json_lines)
        result = []
        async for line in executor.async_execute(cmd):
            result.append(line)

        assert len(result) == 2
        assert json.loads(result[0].decode())["id"] == 1
        assert json.loads(result[1].decode())["id"] == 2

    @pytest.mark.asyncio
    async def test_async_execute_with_error(self):
        """Test async executing command that exits with error."""
        executor = AsyncProcessExecutor()

        cmd = get_false_command()
        with pytest.raises(RuntimeError) as exc_info:
            async for _ in executor.async_execute(cmd):
                pass

        assert exc_info.value.message == "CLI exited with code 1"
        assert exc_info.value.exit_code == 1

    @pytest.mark.asyncio
    async def test_async_execute_with_custom_error(self):
        """Test async executing command with custom error."""
        executor = AsyncProcessExecutor()

        cmd = create_error_command(99, "Async error")
        with pytest.raises(RuntimeError) as exc_info:
            async for _ in executor.async_execute(cmd):
                pass

        assert exc_info.value.exit_code == 99
        # stderr might be empty or contain error text
        assert (
            exc_info.value.stderr is None
            or "error" in exc_info.value.stderr.lower()
            or "Async" in str(exc_info.value.stderr)
        )

    @pytest.mark.asyncio
    async def test_async_with_large_output(self):
        """Test async with large output."""
        executor = AsyncProcessExecutor()
        count = 0
        async for line in executor.async_execute(["seq", "1", "1000"]):
            count += 1

        assert count == 1000

    @pytest.mark.asyncio
    async def test_async_with_unicode(self):
        """Test async with Unicode output."""
        executor = AsyncProcessExecutor()

        messages = ["Test 测试", "Data データ", "Emoji 😀"]
        cmd = get_shell_command() + [f'echo "{messages[0]}\\n{messages[1]}\\n{messages[2]}"']

        result = []
        async for line in executor.async_execute(cmd):
            result.append(line)

        # Check that Unicode characters are present
        combined_output = b"".join(result).decode()
        assert "测试" in combined_output
        assert "データ" in combined_output
        assert "😀" in combined_output


# ========== Integration Tests ==========


class TestExecutorIntegration:
    """Integration tests for executors."""

    def test_sync_executor_streaming(self):
        """Test that sync executor properly streams output."""
        executor = SyncProcessExecutor()

        # Use simple echo with multiple lines
        if IS_WINDOWS:
            cmd = ["cmd.exe", "/c", "for %i in (0 1 2 3 4) do @echo line%i"]
        else:
            cmd = ["sh", "-c", "for i in 0 1 2 3 4; do echo line$i; done"]

        result = []
        for line in executor.execute(cmd):
            result.append(line.decode().strip())

        assert result == [f"line{i}" for i in range(5)]

    @pytest.mark.asyncio
    async def test_async_executor_streaming(self):
        """Test that async executor properly streams output."""
        executor = AsyncProcessExecutor()

        if IS_WINDOWS:
            cmd = ["cmd.exe", "/c", "for %i in (0 1 2 3 4) do @echo async_line%i"]
        else:
            cmd = ["sh", "-c", "for i in 0 1 2 3 4; do echo async_line$i; done"]

        result = []
        async for line in executor.async_execute(cmd):
            result.append(line.decode().strip())

        assert result == [f"async_line{i}" for i in range(5)]

    def test_sync_executor_with_json_stream(self):
        """Test sync executor with JSON output stream (simulating Claude output)."""
        executor = SyncProcessExecutor()

        # Simulate Claude API responses
        json_lines = [
            '{"type": "assistant", "model": "sonnet", "text": "Hello"}',
            '{"type": "assistant", "model": "sonnet", "text": "World"}',
        ]

        cmd = create_json_command(json_lines)

        result = []
        for line in executor.execute(cmd):
            result.append(json.loads(line.decode()))

        assert len(result) == 2
        assert result[0]["text"] == "Hello"
        assert result[1]["text"] == "World"

    @pytest.mark.asyncio
    async def test_async_executor_with_json_stream(self):
        """Test async executor with JSON output stream."""
        executor = AsyncProcessExecutor()

        responses = [
            '{"type": "status", "message": "Processing"}',
            '{"type": "result", "value": 42}',
        ]

        cmd = create_json_command(responses)

        result = []
        async for line in executor.async_execute(cmd):
            result.append(json.loads(line.decode()))

        assert len(result) == 2
        assert result[0]["message"] == "Processing"
        assert result[1]["value"] == 42

    def test_sync_executor_cleanup(self):
        """Test that sync executor properly cleans up processes."""
        executor = SyncProcessExecutor()

        # Execute command that finishes
        list(executor.execute(["echo", "test"]))

        # Executor should be ready for next command
        result = list(executor.execute(["echo", "test2"]))
        assert len(result) == 1
        assert result[0].decode() == "test2\n"

    @pytest.mark.asyncio
    async def test_async_executor_cleanup(self):
        """Test that async executor properly cleans up processes."""
        executor = AsyncProcessExecutor()

        async for _ in executor.async_execute(["echo", "test1"]):
            pass

        # Executor should be ready for next command
        result = []
        async for line in executor.async_execute(["echo", "test2"]):
            result.append(line)

        assert len(result) == 1
        assert result[0].decode() == "test2\n"
