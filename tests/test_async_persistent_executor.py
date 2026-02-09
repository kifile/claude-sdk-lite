"""Tests for AsyncPersistentProcessManager - bidirectional communication.

Uses standard Unix commands (cat, wc, grep, etc.) to test subprocess communication.
"""

import asyncio
import sys

import pytest
from test_helpers import (
    get_cat_command,
    get_grep_command,
    get_head_command,
    get_true_command,
)

from claude_sdk_lite.async_persistent_executor import AsyncPersistentProcessManager

# ========== Helper Functions ==========


async def read_n_lines_async(manager, n, timeout=2.0):
    """Read exactly n lines from manager (async)."""
    lines = []
    async for line in manager.read_lines(timeout=timeout):
        lines.append(line)
        if len(lines) >= n:
            break
    return lines


# ========== Basic Lifecycle Tests ==========


class TestAsyncPersistentProcessManagerLifecycle:
    """Test basic start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_and_stop_cat(self):
        """Test starting and stopping cat process."""
        manager = AsyncPersistentProcessManager()
        assert not manager.is_alive()

        # cat will keep running, reading from stdin and writing to stdout
        await manager.start(get_cat_command())
        assert manager.is_alive()

        await manager.stop()
        assert not manager.is_alive()

    @pytest.mark.asyncio
    async def test_start_when_already_running_raises_error(self):
        """Test that starting when already running raises RuntimeError."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        try:
            with pytest.raises(RuntimeError, match="Process already running"):
                await manager.start(get_cat_command())
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self):
        """Test that stop can be called multiple times safely."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        await manager.stop()
        assert not manager.is_alive()

        # Should not raise
        await manager.stop()
        await manager.stop()

    @pytest.mark.asyncio
    async def test_context_manager_auto_cleanup(self):
        """Test that async context manager automatically cleans up."""
        async with AsyncPersistentProcessManager() as manager:
            await manager.start(get_cat_command())
            assert manager.is_alive()

        # Process should be stopped after exiting context
        assert not manager.is_alive()

    @pytest.mark.asyncio
    async def test_is_alive_returns_false_after_process_exits(self):
        """Test that is_alive returns False after process exits naturally."""
        manager = AsyncPersistentProcessManager()
        # true exits immediately after doing nothing
        await manager.start(get_true_command())

        await asyncio.sleep(0.1)  # Give it time to exit
        assert not manager.is_alive()


# ========== Bidirectional Communication Tests ==========


class TestAsyncBidirectionalCommunication:
    """Test bidirectional stdin/stdout communication using cat."""

    @pytest.mark.asyncio
    async def test_write_and_read_raw_bytes(self):
        """Test writing raw bytes to cat and reading them back."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        try:
            # Write JSON (which becomes bytes in stdin)
            test_data = {"test": "data", "number": 42}
            await manager.write_request(test_data)

            # cat echoes back the exact bytes
            import json

            response = None
            async for line in manager.read_lines(timeout=2.0):
                response = json.loads(line.decode("utf-8"))
                break  # Only read one line

            assert response is not None
            assert response == test_data

        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_multiple_round_trips_with_cat(self):
        """Test multiple write-read cycles with cat."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        try:
            # Send multiple requests
            messages = [
                {"id": 1, "message": "first"},
                {"id": 2, "message": "second"},
                {"id": 3, "message": "third"},
            ]

            for msg in messages:
                await manager.write_request(msg)
                responses = await read_n_lines_async(manager, 1)
                assert len(responses) == 1

                import json

                response = json.loads(responses[0].decode("utf-8"))
                assert response == msg

        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_concurrent_writes_then_reads(self):
        """Test writing multiple requests, then reading all responses."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        try:
            # Send all requests first
            num_requests = 3
            for i in range(num_requests):
                await manager.write_request({"sequence": i})

            # Then read all responses (cat echoes in order)
            import json

            responses = await read_n_lines_async(manager, num_requests)
            responses = [json.loads(r.decode("utf-8")) for r in responses]

            assert len(responses) == num_requests
            assert [r["sequence"] for r in responses] == [0, 1, 2]

        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_write_before_start_raises_error(self):
        """Test that write_request raises error if process not started."""
        manager = AsyncPersistentProcessManager()

        with pytest.raises(RuntimeError, match="Process not running"):
            await manager.write_request({"test": "data"})

    @pytest.mark.asyncio
    async def test_read_before_start_raises_error(self):
        """Test that read_lines raises error if process not started."""
        manager = AsyncPersistentProcessManager()

        with pytest.raises(RuntimeError, match="Process not running"):
            async for _ in manager.read_lines(timeout=1.0):
                pass  # Should error before reading


# ========== Error Handling Tests ==========


class TestAsyncErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_process_exit_detection_with_echo(self):
        """Test detection when process exits after one echo."""
        manager = AsyncPersistentProcessManager()
        # Use a shell command that exits after processing stdin
        # 'head -1' reads one line then exits
        await manager.start(get_head_command(1))

        try:
            # First request should succeed
            await manager.write_request({"test": "first"})
            responses = await read_n_lines_async(manager, 1)
            assert len(responses) == 1

            # Process has exited after head -1
            # Give stdout_reader time to detect EOF
            await asyncio.sleep(0.1)

            # Process should be dead now
            assert not manager.is_alive()

            # Next read should get EOF immediately (no error, just EOF)
            count = 0
            async for _ in manager.read_lines(timeout=1.0):
                count += 1
            assert count == 0  # Got EOF, no data

        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_process_with_nonzero_exit_code(self):
        """Test handling of process that exits with error code."""
        manager = AsyncPersistentProcessManager()
        # Script that writes to stderr and exits with code 42
        script = (
            'import sys; sys.stderr.write("Error occurred\\n"); sys.stderr.flush(); sys.exit(42)'
        )
        await manager.start([sys.executable, "-u", "-c", script])

        try:
            await asyncio.sleep(0.2)  # Let process exit

            # Process should be dead
            assert not manager.is_alive()

            # Try to read, should get EOF (not raise, just EOF)
            # Check stderr was captured
            stderr_lines = await manager.get_stderr()
            assert "Error occurred" in "\n".join(stderr_lines)

            # Reading should return EOF (no error, just no data)
            count = 0
            async for _ in manager.read_lines(timeout=0.5):
                count += 1
            assert count == 0  # Got EOF

        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_stderr_capture(self):
        """Test that stderr is captured."""
        manager = AsyncPersistentProcessManager()
        # Script that writes warnings to stderr, echoes stdin
        script = """
import sys
for line in sys.stdin:
    sys.stderr.write("Warning: processing line\\n")
    sys.stderr.flush()
    sys.stdout.write(line)
    sys.stdout.flush()
"""
        await manager.start([sys.executable, "-u", "-c", script])

        try:
            await manager.write_request({"test": "data"})
            await read_n_lines_async(manager, 1)

            await asyncio.sleep(0.1)  # Give stderr time to be captured
            stderr_lines = await manager.get_stderr()
            assert any("Warning: processing line" in line for line in stderr_lines)

        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_timeout_with_alive_process(self):
        """Test that timeout doesn't error if process is still alive."""
        manager = AsyncPersistentProcessManager()
        # grep will wait for input
        await manager.start(get_grep_command("pattern"))

        try:
            # Don't send anything, directly test queue timeout behavior
            # grep won't produce output, so queue should be empty
            line = None
            try:
                # Try to get from queue with timeout
                line = await asyncio.wait_for(manager._line_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                pass  # Expected - no data available

            # Should have gotten nothing (line is None or we timed out)
            assert line is None
            assert manager.is_alive()  # grep should still be running

        finally:
            await manager.stop()


# ========== Interrupt Tests ==========


class TestAsyncInterruptFunctionality:
    """Test interrupt signal functionality."""

    @pytest.mark.asyncio
    async def test_write_interrupt_sends_control_request(self):
        """Test that write_interrupt sends control request."""
        manager = AsyncPersistentProcessManager()
        # cat will echo the interrupt request back
        await manager.start(get_cat_command())

        try:
            await manager.write_interrupt()

            # Read the echoed interrupt request
            responses = await read_n_lines_async(manager, 1)
            assert len(responses) == 1

            import json

            response = json.loads(responses[0].decode("utf-8"))
            assert response["type"] == "control_request"
            assert response["subtype"] == "interrupt"

        finally:
            await manager.stop()


# ========== Data Integrity Tests ==========


class TestAsyncDataIntegrity:
    """Test data integrity with real data."""

    @pytest.mark.asyncio
    async def test_large_data_transfer(self):
        """Test handling of large JSON payloads."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        try:
            # Send large data
            large_data = "x" * 10000
            request = {"type": "test", "data": large_data}
            await manager.write_request(request)

            responses = await read_n_lines_async(manager, 1)
            assert len(responses) == 1

            import json

            response = json.loads(responses[0].decode("utf-8"))
            assert response["data"] == large_data

        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_unicode_and_special_characters(self):
        """Test handling of Unicode and special characters."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        try:
            test_strings = [
                "Unicode: 你好世界 🎉",
                "Newlines: line1\nline2",
                "Tabs: col1\tcol2",
                'Quotes: "escaped"',
            ]

            for test_str in test_strings:
                request = {"message": test_str}
                await manager.write_request(request)

                responses = await read_n_lines_async(manager, 1)
                assert len(responses) == 1

                import json

                response = json.loads(responses[0].decode("utf-8"))
                assert response["message"] == test_str

        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_json_formatting_preserved(self):
        """Test that JSON structure is preserved through round-trip."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        try:
            # Complex nested structure
            complex_request = {
                "type": "complex",
                "nested": {"level1": {"level2": {"data": [1, 2, 3], "metadata": {"key": "value"}}}},
                "items": [
                    {"id": 1, "name": "first"},
                    {"id": 2, "name": "second"},
                ],
            }
            await manager.write_request(complex_request)

            responses = await read_n_lines_async(manager, 1)
            assert len(responses) == 1

            import json

            response = json.loads(responses[0].decode("utf-8"))
            assert response == complex_request

        finally:
            await manager.stop()


# ========== Integration Scenarios ==========


class TestAsyncIntegrationScenarios:
    """Integration tests for realistic usage patterns."""

    @pytest.mark.asyncio
    async def test_session_like_conversation(self):
        """Test a realistic session-like interaction pattern."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        try:
            # Simulate a conversation
            messages = [
                {"role": "user", "content": "hello"},
                {"role": "user", "content": "how are you?"},
                {"role": "user", "content": "goodbye"},
            ]

            import json

            responses = []
            for msg in messages:
                await manager.write_request(msg)
                async for line in manager.read_lines(timeout=2.0):
                    response = json.loads(line.decode("utf-8"))
                    responses.append(response)
                    break  # Only read one response per message

            assert len(responses) == 3
            for i, response in enumerate(responses):
                assert response["content"] == messages[i]["content"]

        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_reusable_after_stop(self):
        """Test that manager can be reused after stop."""
        manager = AsyncPersistentProcessManager()

        # First session
        await manager.start(get_cat_command())
        await manager.write_request({"session": 1})
        await read_n_lines_async(manager, 1)
        await manager.stop()

        # Second session (should work)
        await manager.start(get_cat_command())
        await manager.write_request({"session": 2})
        responses = await read_n_lines_async(manager, 1)
        assert len(responses) == 1
        await manager.stop()

    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_cleanup(self):
        """Test graceful shutdown and resource cleanup."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        # Do some work
        import json

        for i in range(3):
            await manager.write_request({"id": i})
            responses = await read_n_lines_async(manager, 1)
            assert len(responses) == 1
            assert json.loads(responses[0].decode("utf-8"))["id"] == i

        # Stop should cleanup cleanly
        await manager.stop()
        assert not manager.is_alive()


# ========== Generator Behavior Tests ==========


class TestAsyncGeneratorBehavior:
    """Test async generator behavior of read_lines."""

    @pytest.mark.asyncio
    async def test_generator_can_be_closed_early(self):
        """Test that generator can be closed before consuming all lines."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        try:
            # Send request
            await manager.write_request({"test": "data"})

            # Only read first line then close
            count = 0
            async for line in manager.read_lines(timeout=2.0):
                count += 1
                if count >= 1:
                    break

            assert count == 1
            assert manager.is_alive()  # cat should still be running

        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_read_lines_with_timeout(self):
        """Test read_lines respects timeout parameter."""
        manager = AsyncPersistentProcessManager()
        await manager.start(get_cat_command())

        try:
            await manager.write_request({"test": "timeout"})

            # Read with sufficient timeout
            responses = await read_n_lines_async(manager, 1)
            assert len(responses) == 1

        finally:
            await manager.stop()


# Import asyncio for sleep
import asyncio
