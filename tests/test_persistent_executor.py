"""Tests for PersistentProcessManager - bidirectional communication.

Uses standard Unix commands (cat, wc, grep, etc.) to test subprocess communication.
"""

import sys
import time

import pytest
from test_helpers import (
    get_cat_command,
    get_grep_command,
    get_head_command,
    get_true_command,
)

from claude_sdk_lite.persistent_executor import PersistentProcessManager

# ========== Helper Functions ==========


def read_n_lines(manager, n, timeout=2.0):
    """Read exactly n lines from manager."""
    lines = []
    for line in manager.read_lines(timeout=timeout):
        lines.append(line)
        if len(lines) >= n:
            break
    return lines


# ========== Basic Lifecycle Tests ==========


class TestPersistentProcessManagerLifecycle:
    """Test basic start/stop lifecycle."""

    def test_start_and_stop_cat(self):
        """Test starting and stopping cat process."""
        manager = PersistentProcessManager()
        assert not manager.is_alive()

        # cat will keep running, reading from stdin and writing to stdout
        manager.start(get_cat_command())
        assert manager.is_alive()

        manager.stop()
        assert not manager.is_alive()

    def test_start_when_already_running_raises_error(self):
        """Test that starting when already running raises RuntimeError."""
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

        try:
            with pytest.raises(RuntimeError, match="Process already running"):
                manager.start(get_cat_command())
        finally:
            manager.stop()

    def test_stop_is_idempotent(self):
        """Test that stop can be called multiple times safely."""
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

        manager.stop()
        assert not manager.is_alive()

        # Should not raise
        manager.stop()
        manager.stop()

    def test_context_manager_auto_cleanup(self):
        """Test that context manager automatically cleans up."""
        with PersistentProcessManager() as manager:
            manager.start(get_cat_command())
            assert manager.is_alive()

        # Process should be stopped after exiting context
        assert not manager.is_alive()

    def test_is_alive_returns_false_after_process_exits(self):
        """Test that is_alive returns False after process exits naturally."""
        manager = PersistentProcessManager()
        # true exits immediately after doing nothing
        manager.start(get_true_command())

        time.sleep(0.1)  # Give it time to exit
        assert not manager.is_alive()


# ========== Bidirectional Communication Tests ==========


class TestBidirectionalCommunication:
    """Test bidirectional stdin/stdout communication using cat."""

    def test_write_and_read_raw_bytes(self):
        """Test writing raw bytes to cat and reading them back.

        Note: write_request sends JSON, but cat just echoes raw bytes.
        So we test the underlying bidirectional communication.
        """
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

        try:
            # Write JSON (which becomes bytes in stdin)
            test_data = {"test": "data", "number": 42}
            manager.write_request(test_data)

            # cat echoes back the exact bytes
            # Read only one response then stop (cat keeps running)
            import json

            response = None
            for line in manager.read_lines(timeout=2.0):
                response = json.loads(line.decode("utf-8"))
                break  # Only read one line

            assert response is not None
            assert response == test_data

        finally:
            manager.stop()

    def test_multiple_round_trips_with_cat(self):
        """Test multiple write-read cycles with cat."""
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

        try:
            # Send multiple requests
            messages = [
                {"id": 1, "message": "first"},
                {"id": 2, "message": "second"},
                {"id": 3, "message": "third"},
            ]

            for msg in messages:
                manager.write_request(msg)
                responses = read_n_lines(manager, 1)
                assert len(responses) == 1

                import json

                response = json.loads(responses[0].decode("utf-8"))
                assert response == msg

        finally:
            manager.stop()

    def test_concurrent_writes_then_reads(self):
        """Test writing multiple requests, then reading all responses."""
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

        try:
            # Send all requests first
            num_requests = 3
            for i in range(num_requests):
                manager.write_request({"sequence": i})

            # Then read all responses (cat echoes in order)
            import json

            responses = read_n_lines(manager, num_requests)
            responses = [json.loads(r.decode("utf-8")) for r in responses]

            assert len(responses) == num_requests
            assert [r["sequence"] for r in responses] == [0, 1, 2]

        finally:
            manager.stop()

    def test_write_before_start_raises_error(self):
        """Test that write_request raises error if process not started."""
        manager = PersistentProcessManager()

        with pytest.raises(RuntimeError, match="Process not running"):
            manager.write_request({"test": "data"})

    def test_read_before_start_raises_error(self):
        """Test that read_lines raises error if process not started."""
        manager = PersistentProcessManager()

        with pytest.raises(RuntimeError, match="Process not running"):
            list(manager.read_lines(timeout=1.0))  # Should error before reading


# ========== Error Handling Tests ==========


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_process_exit_detection_with_echo(self):
        """Test detection when process exits after one echo."""
        manager = PersistentProcessManager()
        # Use a shell command that exits after processing stdin
        # 'head -1' reads one line then exits
        manager.start(get_head_command(1))

        try:
            # First request should succeed
            manager.write_request({"test": "first"})
            responses = read_n_lines(manager, 1)
            assert len(responses) == 1

            # Process has exited after head -1
            # Give stdout_reader time to detect EOF
            import time

            time.sleep(0.1)

            # Process should be dead now
            assert not manager.is_alive()

            # Next read should get EOF immediately (no error, just EOF)
            # The EOF sentinel (None) causes read_lines to exit cleanly
            count = 0
            for _ in manager.read_lines(timeout=1.0):
                count += 1
            assert count == 0  # Got EOF, no data

        finally:
            manager.stop()

    def test_process_with_nonzero_exit_code(self):
        """Test handling of process that exits with error code."""
        manager = PersistentProcessManager()
        # Script that writes to stderr and exits with code 42
        script = (
            'import sys; sys.stderr.write("Error occurred\\n"); sys.stderr.flush(); sys.exit(42)'
        )
        manager.start([sys.executable, "-u", "-c", script])

        try:
            time.sleep(0.2)  # Let process exit

            # Process should be dead
            assert not manager.is_alive()

            # Try to read, should get EOF (not raise, just EOF)
            # Check stderr was captured
            stderr_lines = manager.get_stderr()
            assert "Error occurred" in "\n".join(stderr_lines)

            # Reading should return EOF (no error, just no data)
            count = 0
            for _ in manager.read_lines(timeout=0.5):
                count += 1
            assert count == 0  # Got EOF

        finally:
            manager.stop()

    def test_stderr_capture(self):
        """Test that stderr is captured."""
        manager = PersistentProcessManager()
        # Script that writes warnings to stderr, echoes stdin
        script = """
import sys
for line in sys.stdin:
    sys.stderr.write("Warning: processing line\\n")
    sys.stderr.flush()
    sys.stdout.write(line)
    sys.stdout.flush()
"""
        manager.start([sys.executable, "-u", "-c", script])

        try:
            manager.write_request({"test": "data"})
            read_n_lines(manager, 1)

            time.sleep(0.1)  # Give stderr time to be captured
            stderr_lines = manager.get_stderr()
            assert any("Warning: processing line" in line for line in stderr_lines)

        finally:
            manager.stop()

    def test_timeout_with_alive_process(self):
        """Test that timeout doesn't error if process is still alive."""
        manager = PersistentProcessManager()
        # grep will wait for input
        manager.start(get_grep_command("pattern"))

        try:
            # Don't send anything, directly test queue timeout behavior
            # grep won't produce output, so queue should be empty
            import queue as queue_module

            line = None
            try:
                # Try to get from queue with timeout
                line = manager._line_queue.get(timeout=0.5)
            except queue_module.Empty:
                pass  # Expected - no data available

            # Should have gotten nothing (line is None or we timed out)
            assert line is None
            assert manager.is_alive()  # grep should still be running

        finally:
            manager.stop()


# ========== Interrupt Tests ==========


class TestInterruptFunctionality:
    """Test interrupt signal functionality."""

    def test_write_interrupt_sends_control_request(self):
        """Test that write_interrupt sends control request."""
        manager = PersistentProcessManager()
        # cat will echo the interrupt request back
        manager.start(get_cat_command())

        try:
            manager.write_interrupt()

            # Read the echoed interrupt request
            responses = read_n_lines(manager, 1)
            assert len(responses) == 1

            import json

            response = json.loads(responses[0].decode("utf-8"))
            assert response["type"] == "control_request"
            assert response["subtype"] == "interrupt"

        finally:
            manager.stop()


# ========== Data Integrity Tests ==========


class TestDataIntegrity:
    """Test data integrity with real data."""

    def test_large_data_transfer(self):
        """Test handling of large JSON payloads."""
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

        try:
            # Send large data
            large_data = "x" * 10000
            request = {"type": "test", "data": large_data}
            manager.write_request(request)

            responses = read_n_lines(manager, 1)
            assert len(responses) == 1

            import json

            response = json.loads(responses[0].decode("utf-8"))
            assert response["data"] == large_data

        finally:
            manager.stop()

    def test_unicode_and_special_characters(self):
        """Test handling of Unicode and special characters."""
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

        try:
            test_strings = [
                "Unicode: 你好世界 🎉",
                "Newlines: line1\nline2",
                "Tabs: col1\tcol2",
                'Quotes: "escaped"',
            ]

            for test_str in test_strings:
                request = {"message": test_str}
                manager.write_request(request)

                responses = read_n_lines(manager, 1)
                assert len(responses) == 1

                import json

                response = json.loads(responses[0].decode("utf-8"))
                assert response["message"] == test_str

        finally:
            manager.stop()

    def test_json_formatting_preserved(self):
        """Test that JSON structure is preserved through round-trip."""
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

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
            manager.write_request(complex_request)

            responses = read_n_lines(manager, 1)
            assert len(responses) == 1

            import json

            response = json.loads(responses[0].decode("utf-8"))
            assert response == complex_request

        finally:
            manager.stop()


# ========== Integration Scenarios ==========


class TestIntegrationScenarios:
    """Integration tests for realistic usage patterns."""

    def test_session_like_conversation(self):
        """Test a realistic session-like interaction pattern."""
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

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
                manager.write_request(msg)
                for line in manager.read_lines(timeout=2.0):
                    response = json.loads(line.decode("utf-8"))
                    responses.append(response)
                    break  # Only read one response per message

            assert len(responses) == 3
            for i, response in enumerate(responses):
                assert response["content"] == messages[i]["content"]

        finally:
            manager.stop()

    def test_reusable_after_stop(self):
        """Test that manager can be reused after stop."""
        manager = PersistentProcessManager()

        # First session
        manager.start(get_cat_command())
        manager.write_request({"session": 1})
        read_n_lines(manager, 1)
        manager.stop()

        # Second session (should work)
        manager.start(get_cat_command())
        manager.write_request({"session": 2})
        responses = read_n_lines(manager, 1)
        assert len(responses) == 1
        manager.stop()

    def test_graceful_shutdown_with_cleanup(self):
        """Test graceful shutdown and resource cleanup."""
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

        # Do some work
        import json

        for i in range(3):
            manager.write_request({"id": i})
            responses = read_n_lines(manager, 1)
            assert len(responses) == 1
            assert json.loads(responses[0].decode("utf-8"))["id"] == i

        # Stop should cleanup cleanly
        manager.stop()
        assert not manager.is_alive()


# ========== Generator Behavior Tests ==========


class TestGeneratorBehavior:
    """Test generator behavior of read_lines."""

    def test_generator_can_be_closed_early(self):
        """Test that generator can be closed before consuming all lines."""
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

        try:
            # Send request
            manager.write_request({"test": "data"})

            # Only read first line then close
            count = 0
            for line in manager.read_lines(timeout=2.0):
                count += 1
                if count >= 1:
                    break

            assert count == 1
            assert manager.is_alive()  # cat should still be running

        finally:
            manager.stop()

    def test_read_lines_with_timeout(self):
        """Test read_lines respects timeout parameter."""
        manager = PersistentProcessManager()
        manager.start(get_cat_command())

        try:
            manager.write_request({"test": "timeout"})

            # Read with sufficient timeout
            responses = read_n_lines(manager, 1)
            assert len(responses) == 1

        finally:
            manager.stop()
