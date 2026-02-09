"""Integration tests for ClaudeClient with real subprocess interactions.

These tests use simple commands (cat, echo, grep) to simulate Claude CLI behavior
and test the full client functionality including message streaming, error handling,
and session management.
"""

import asyncio
import json
import sys
import time

import pytest

from claude_sdk_lite import AsyncClaudeClient, ClaudeClient, ClaudeOptions
from claude_sdk_lite.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
)


def create_echo_script(num_lines=1, add_result=False):
    """Create a Python script that echoes input and optionally adds a result message.

    Args:
        num_lines: Number of lines to read and echo
        add_result: Whether to append a result message

    Returns:
        Script content as string
    """
    lines = ["import sys", "import json"]
    lines.append("")
    lines.append(f"# Read and echo {num_lines} line(s)")

    for i in range(num_lines):
        lines.append(f"line{i} = sys.stdin.readline()")
        lines.append(f"if line{i}:")
        lines.append(f"    print(line{i}, end='')")
        lines.append(f"    sys.stdout.flush()")

    if add_result:
        lines.append("")
        lines.append("# Print result message")
        lines.append("result_msg = {")
        lines.append('    "type": "result",')
        lines.append('    "subtype": "complete",')
        lines.append('    "duration_ms": 100,')
        lines.append('    "duration_api_ms": 50,')
        lines.append('    "is_error": False,')
        lines.append('    "num_turns": 1,')
        lines.append('    "session_id": "test-session"')
        lines.append("}")
        lines.append("print(json.dumps(result_msg))")

    return "\n".join(lines)


class TestClaudeClientRealSubprocess:
    """Integration tests using real subprocess commands."""

    def test_full_lifecycle_with_cat(self):
        """Test full connect/query/disconnect lifecycle using cat."""
        # We'll manually manage the process to test without actual Claude CLI
        options = ClaudeOptions()
        client = ClaudeClient(options=options)

        # Replace the command building for testing
        client._build_command
        client._build_command = lambda: ["cat"]

        try:
            # Connect
            client.connect()
            assert client.is_connected

            # Send a message
            test_message = {"test": "data", "content": "hello"}
            client._manager.write_request(test_message)

            # Read response (cat echoes back)
            responses = []
            for line in client._manager.read_lines(timeout=1.0):
                data = json.loads(line.decode())
                responses.append(data)
                if len(responses) >= 1:
                    break

            assert len(responses) == 1
            assert responses[0] == test_message

        finally:
            client.disconnect()
            assert not client.is_connected

    def test_multiple_queries_in_session(self):
        """Test multiple queries within the same session."""
        options = ClaudeOptions()
        client = ClaudeClient(options=options)
        client._build_command = lambda: ["cat"]

        try:
            client.connect()

            # Send multiple messages
            messages = [
                {"seq": 1, "text": "first"},
                {"seq": 2, "text": "second"},
                {"seq": 3, "text": "third"},
            ]

            for msg in messages:
                client._manager.write_request(msg)
                responses = []
                for line in client._manager.read_lines(timeout=1.0):
                    data = json.loads(line.decode())
                    responses.append(data)
                    break

                assert len(responses) == 1
                assert responses[0]["seq"] == msg["seq"]

        finally:
            client.disconnect()

    def test_session_id_persists_across_queries(self):
        """Test that session_id remains constant across multiple queries."""
        options = ClaudeOptions()
        client = ClaudeClient(options=options)
        session_id = client.session_id

        client._build_command = lambda: ["cat"]

        try:
            client.connect()

            # Query 1
            client._manager.write_request({"q": 1})
            for _ in client._manager.read_lines(timeout=1.0):
                break

            # Query 2
            client._manager.write_request({"q": 2})
            for _ in client._manager.read_lines(timeout=1.0):
                break

            # Session ID should be unchanged
            assert client.session_id == session_id

        finally:
            client.disconnect()

    def test_interrupt_signal(self):
        """Test sending interrupt signal."""
        options = ClaudeOptions()
        client = ClaudeClient(options=options)
        client._build_command = lambda: ["cat"]

        try:
            client.connect()
            client.interrupt()

            # Read the interrupt message
            responses = []
            for line in client._manager.read_lines(timeout=1.0):
                data = json.loads(line.decode())
                responses.append(data)
                break

            assert len(responses) == 1
            assert responses[0]["type"] == "control_request"
            assert responses[0]["subtype"] == "interrupt"

        finally:
            client.disconnect()


class TestClaudeClientMessageHandling:
    """Test message parsing and handling in real scenarios."""

    def test_parse_assistant_message_from_cat(self):
        """Test parsing assistant messages echoed by cat."""
        options = ClaudeOptions()
        client = ClaudeClient(options=options)

        # Use Python script that echoes input and adds a result message
        script = """
import sys
import json

# Read one line from stdin
line = sys.stdin.readline()
if line:
    # Echo it back
    print(line, end='')
    sys.stdout.flush()

# Print a result message to signal completion
result_msg = {
    "type": "result",
    "subtype": "complete",
    "duration_ms": 100,
    "duration_api_ms": 50,
    "is_error": False,
    "num_turns": 1,
    "session_id": "test-session"
}
print(json.dumps(result_msg))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        # Create a real assistant message
        assistant_msg = {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5",
                "content": [
                    {"type": "text", "text": "Hello, world!"},
                    {"type": "thinking", "thinking": "Let me think...", "signature": "sig"},
                ],
            },
        }

        try:
            client.connect()
            client._manager.write_request(assistant_msg)

            messages = []
            for line in client._manager.read_lines(timeout=2.0):
                from claude_sdk_lite.message_parser import parse_message

                data = json.loads(line.decode())
                msg = parse_message(data)
                messages.append(msg)
                if isinstance(msg, ResultMessage):
                    break

            # Should get back the assistant message
            assert len(messages) >= 1
            assert isinstance(messages[0], AssistantMessage)
            assert len(messages[0].content) == 2
            assert isinstance(messages[0].content[0], TextBlock)
            assert messages[0].content[0].text == "Hello, world!"

        finally:
            client.disconnect()

    def test_handle_malformed_json_gracefully(self):
        """Test that malformed JSON is handled gracefully."""
        import os

        # Create a temporary file with mixed valid/invalid JSON
        import tempfile

        from claude_sdk_lite.message_parser import MessageParseError, parse_message

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_file = f.name
            f.write('{"type": "assistant", "message": {"model": "sonnet", "content": []}}\n')
            f.write("invalid json line\n")
            f.write(
                '{"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": false, "num_turns": 1, "session_id": "test"}\n'
            )

        try:
            options = ClaudeOptions()
            client = ClaudeClient(options=options)

            # Use cat to output the file content once
            # This simulates a process that outputs all messages then exits cleanly
            client._build_command = lambda: ["cat", temp_file]

            client.connect()

            messages = []
            line_count = 0
            for line in client._manager.read_lines(timeout=2.0):
                line_count += 1
                line_str = line.decode().strip()
                if not line_str:
                    continue

                try:
                    data = json.loads(line_str)
                    msg = parse_message(data)
                    messages.append(msg)
                    if isinstance(msg, ResultMessage):
                        break
                except (json.JSONDecodeError, MessageParseError):
                    # Skip invalid messages
                    pass

            # Should get 2 valid messages (assistant + result)
            assert (
                len(messages) == 2
            ), f"Expected 2 messages, got {len(messages)}. Read {line_count} lines."
            assert isinstance(messages[0], AssistantMessage)
            assert isinstance(messages[1], ResultMessage)

            client.disconnect()

        finally:
            os.unlink(temp_file)


class TestClaudeClientErrorScenarios:
    """Test error handling and edge cases."""

    def test_process_during_query(self):
        """Test behavior when process exits during query."""
        options = ClaudeOptions()
        client = ClaudeClient(options=options)

        # Script that exits after processing one message
        script = """
import sys
line = sys.stdin.readline()
if line:
    print(line, end='')
    sys.stdout.flush()
# Exit immediately
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()
            client._manager.write_request({"test": "data"})

            # Should get one response then EOF
            count = 0
            for line in client._manager.read_lines(timeout=1.0):
                count += 1
                if count >= 1:
                    break

            assert count == 1
            time.sleep(0.1)  # Let process exit
            assert not client.is_connected

        finally:
            client.disconnect()

    def test_query_after_reconnect(self):
        """Test that client can be reused after disconnect."""
        options = ClaudeOptions()
        client = ClaudeClient(options=options)
        client._build_command = lambda: ["cat"]

        try:
            # First session
            client.connect()
            client._manager.write_request({"session": 1})
            for _ in client._manager.read_lines(timeout=1.0):
                break
            client.disconnect()

            # Second session
            client.connect()
            client._manager.write_request({"session": 2})
            responses = []
            for line in client._manager.read_lines(timeout=1.0):
                responses.append(json.loads(line.decode()))
                break

            assert len(responses) == 1
            assert responses[0]["session"] == 2

        finally:
            client.disconnect()


class TestClaudeClientContextManager:
    """Test context manager behavior."""

    def test_context_manager_cleanup_on_error(self):
        """Test that context manager cleans up even on error."""
        options = ClaudeOptions()
        client = ClaudeClient(options=options)
        client._build_command = lambda: ["cat"]

        with pytest.raises(ValueError):
            with client:
                client.connect()
                assert client.is_connected
                raise ValueError("Test error")

        # Should be disconnected
        assert not client.is_connected

    def test_nested_context_managers(self):
        """Test using multiple clients in nested contexts."""
        options1 = ClaudeOptions()
        options2 = ClaudeOptions()

        client1 = ClaudeClient(options=options1)
        client2 = ClaudeClient(options=options2)

        client1._build_command = lambda: ["cat"]
        client2._build_command = lambda: ["cat"]

        with client1:
            with client2:
                assert client1.is_connected
                assert client2.is_connected
                assert client1.session_id != client2.session_id

            # client2 disconnected, client1 still connected
            assert client1.is_connected
            assert not client2.is_connected

        # Both disconnected
        assert not client1.is_connected
        assert not client2.is_connected


class TestClaudeClientStderrCapture:
    """Test stderr capture functionality."""

    def test_stderr_is_captured(self):
        """Test that stderr output is captured."""
        options = ClaudeOptions()
        client = ClaudeClient(options=options)

        # Script that writes to stderr
        script = """
import sys
print('stdout message', end='')
sys.stderr.write('stderr message\\n')
sys.stderr.flush()
print('{"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": false, "num_turns": 1, "session_id": "test"}')
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()

            # Consume all output
            for _ in client._manager.read_lines(timeout=1.0):
                pass

            # Check stderr
            stderr = client.stderr_output
            assert len(stderr) > 0
            assert any("stderr message" in line for line in stderr)

        finally:
            client.disconnect()


class TestClaudeClientLargeData:
    """Test handling of large data."""

    def test_large_message_handling(self):
        """Test handling of large JSON messages."""
        options = ClaudeOptions()
        client = ClaudeClient(options=options)
        client._build_command = lambda: ["cat"]

        # Create a large message
        large_text = "x" * 10000
        large_message = {
            "type": "assistant",
            "message": {"model": "sonnet", "content": [{"type": "text", "text": large_text}]},
        }

        try:
            client.connect()
            client._manager.write_request(large_message)

            responses = []
            for line in client._manager.read_lines(timeout=2.0):
                data = json.loads(line.decode())
                responses.append(data)
                if len(responses) >= 1:
                    break

            assert len(responses) == 1
            assert responses[0]["message"]["content"][0]["text"] == large_text

        finally:
            client.disconnect()

    def test_multiple_messages_in_sequence(self):
        """Test sending many messages in sequence."""
        options = ClaudeOptions()
        client = ClaudeClient(options=options)
        client._build_command = lambda: ["cat"]

        try:
            client.connect()

            # Send 100 messages
            for i in range(100):
                client._manager.write_request({"index": i})

                responses = []
                for line in client._manager.read_lines(timeout=1.0):
                    data = json.loads(line.decode())
                    responses.append(data)
                    break

                assert len(responses) == 1
                assert responses[0]["index"] == i

        finally:
            client.disconnect()


class TestClaudeClientTimeouts:
    """Test timeout handling."""

    def test_read_timeout_with_alive_process(self):
        """Test that timeout works correctly - process exits after output."""
        options = ClaudeOptions()
        client = ClaudeClient(options=options)
        # Use 'echo' which outputs one line then exits (EOF)
        client._build_command = lambda: ["echo", '{"test": "data"}']

        try:
            client.connect()

            # Should be able to read the echoed line and then receive EOF
            count = 0
            for line in client._manager.read_lines(timeout=0.5):
                count += 1
                # read_lines should exit when process closes (EOF sentinel)

            # Should have received 1 line before EOF
            assert count == 1
            # Process should have exited
            assert not client.is_connected

        finally:
            client.disconnect()


class TestAsyncClaudeClientRealSubprocess:
    """Integration tests for AsyncClaudeClient using real subprocess commands."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_cat(self):
        """Test full connect/query/disconnect lifecycle using cat."""
        options = ClaudeOptions()
        client = AsyncClaudeClient(options=options)
        client._build_command = lambda: ["cat"]

        try:
            # Connect
            await client.connect()
            assert client.is_connected

            # Send a message
            test_message = {"test": "data", "content": "hello"}
            await client._manager.write_request(test_message)

            # Read response (cat echoes back)
            responses = []
            async for line in client._manager.read_lines(timeout=1.0):
                data = json.loads(line.decode())
                responses.append(data)
                if len(responses) >= 1:
                    break

            assert len(responses) == 1
            assert responses[0] == test_message

        finally:
            await client.disconnect()
            assert not client.is_connected

    @pytest.mark.asyncio
    async def test_multiple_queries_in_session(self):
        """Test multiple queries within the same session."""
        options = ClaudeOptions()
        client = AsyncClaudeClient(options=options)
        client._build_command = lambda: ["cat"]

        try:
            await client.connect()

            # Send multiple messages
            messages = [
                {"seq": 1, "text": "first"},
                {"seq": 2, "text": "second"},
                {"seq": 3, "text": "third"},
            ]

            for msg in messages:
                await client._manager.write_request(msg)
                responses = []
                async for line in client._manager.read_lines(timeout=1.0):
                    data = json.loads(line.decode())
                    responses.append(data)
                    break

                assert len(responses) == 1
                assert responses[0]["seq"] == msg["seq"]

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager behavior."""
        options = ClaudeOptions()
        client = AsyncClaudeClient(options=options)
        client._build_command = lambda: ["cat"]

        async with client:
            assert client.is_connected
            await client._manager.write_request({"test": "data"})

            responses = []
            async for line in client._manager.read_lines(timeout=1.0):
                responses.append(json.loads(line.decode()))
                break

            assert len(responses) == 1

        # Should be disconnected after context
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_async_query_collects_messages(self):
        """Test that query() method collects all messages."""
        options = ClaudeOptions()
        client = AsyncClaudeClient(options=options)

        # Use echo to generate some output
        script = """
import sys
print('{"type": "assistant", "message": {"model": "test", "content": [{"type": "text", "text": "Hello"}]}}')
print('{"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": false, "num_turns": 1, "session_id": "test"}')
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            await client.connect()

            # This would normally call query_stream and collect
            # For testing, we manually consume
            messages = []
            async for line in client._manager.read_lines(timeout=1.0):
                from claude_sdk_lite.message_parser import parse_message

                data = json.loads(line.decode())
                msg = parse_message(data)
                messages.append(msg)
                if isinstance(msg, ResultMessage):
                    break

            assert len(messages) == 2
            assert isinstance(messages[0], AssistantMessage)
            assert isinstance(messages[1], ResultMessage)

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_concurrent_clients(self):
        """Test running multiple async clients concurrently."""
        options1 = ClaudeOptions()
        options2 = ClaudeOptions()

        client1 = AsyncClaudeClient(options=options1)
        client2 = AsyncClaudeClient(options=options2)

        client1._build_command = lambda: ["cat"]
        client2._build_command = lambda: ["cat"]

        async def use_client(client, session_id):
            async with client:
                await client._manager.write_request({"session": session_id})
                responses = []
                async for line in client._manager.read_lines(timeout=1.0):
                    responses.append(json.loads(line.decode()))
                    break
                return responses[0]

        # Run both clients concurrently
        results = await asyncio.gather(
            use_client(client1, 1),
            use_client(client2, 2),
        )

        assert results[0]["session"] == 1
        assert results[1]["session"] == 2
        assert client1.session_id != client2.session_id

    @pytest.mark.asyncio
    async def test_async_interrupt(self):
        """Test async interrupt functionality."""
        options = ClaudeOptions()
        client = AsyncClaudeClient(options=options)
        client._build_command = lambda: ["cat"]

        try:
            await client.connect()
            await client.interrupt()

            # Read the interrupt message
            responses = []
            async for line in client._manager.read_lines(timeout=1.0):
                data = json.loads(line.decode())
                responses.append(data)
                break

            assert len(responses) == 1
            assert responses[0]["type"] == "control_request"
            assert responses[0]["subtype"] == "interrupt"

        finally:
            await client.disconnect()


class TestClientComparison:
    """Compare sync and async client behavior."""

    def test_sync_async_equivalent_session_id_generation(self):
        """Test that sync and async clients generate session IDs the same way."""
        options = ClaudeOptions()

        sync_client = ClaudeClient(options=options)
        async_client = AsyncClaudeClient(options=ClaudeOptions())

        # Both should generate valid UUIDs
        import uuid

        uuid.UUID(sync_client.session_id)
        uuid.UUID(async_client.session_id)

        # Should be different (random)
        assert sync_client.session_id != async_client.session_id

    @pytest.mark.asyncio
    async def test_sync_async_same_command_building(self):
        """Test that sync and async build commands the same way."""
        # Use same session_id for both clients
        session_id = "test-session-123"
        options = ClaudeOptions(model="sonnet", session_id=session_id)

        sync_client = ClaudeClient(options=options)
        async_client = AsyncClaudeClient(options=ClaudeOptions(model="sonnet", session_id=session_id))

        sync_cmd = sync_client._build_command()
        async_cmd = async_client._build_command()

        assert sync_cmd == async_cmd
        assert "--model" in sync_cmd
        assert "sonnet" in sync_cmd
