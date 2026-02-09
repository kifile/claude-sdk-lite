"""Integration tests for ClaudeClient with real subprocess interactions.

These tests use simple commands (cat, echo, grep) to simulate Claude CLI behavior
and test the full client functionality including message streaming, error handling,
and session management with the new message handler architecture.
"""

import asyncio
import sys
import threading
import time

import pytest
from test_helpers import (
    get_cat_command,
)

from claude_sdk_lite import (
    AsyncClaudeClient,
    AsyncDefaultMessageHandler,
    ClaudeClient,
    ClaudeOptions,
    DefaultMessageHandler,
    MessageEventListener,
)
from claude_sdk_lite.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
)


def create_echo_script(num_lines=1, add_result=False):
    """Create a shell command that echoes input and optionally adds a result message.

    Args:
        num_lines: Number of echo commands to include
        add_result: Whether to append a result message

    Returns:
        List of command arguments for subprocess
    """
    # Use Python script for cross-platform compatibility
    echo_cmds = []
    for i in range(num_lines):
        echo_cmds.append(f'print(json.dumps({{"seq": {i}, "text": "message{i}"}}))')

    # Add result message if requested
    if add_result:
        echo_cmds.append(
            'print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test-session"}))'
        )

    script = f"import json; " + "; ".join(echo_cmds)
    return [sys.executable, "-c", script]


class TestClaudeClientRealSubprocess:
    """Integration tests using real subprocess commands."""

    def test_full_lifecycle_with_cat(self):
        """Test full connect/query/disconnect lifecycle using cat."""
        options = ClaudeOptions()
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script to output messages after reading stdin
        script = """
import sys, json
line = sys.stdin.readline()
if line:
    data = json.loads(line)
    print(json.dumps(data))
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            # Connect - this starts the listener thread
            client.connect()
            assert client.is_connected

            # Send a message and get response
            test_message = {"type": "test", "content": "hello"}
            client._manager.write_request(test_message)

            # The listener thread will capture the message
            time.sleep(0.3)  # Give listener time to read

            # Check that handler received the message
            messages = client.message_handler.get_messages()
            assert len(messages) >= 1

        finally:
            client.disconnect()
            assert not client.is_connected

    def test_multiple_queries_in_session(self):
        """Test multiple queries within the same session."""
        options = ClaudeOptions()
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script with a loop that reads stdin and outputs messages 3 times
        script = """
import sys, json
for i in range(1, 4):
    line = sys.stdin.readline()
    if line:
        data = json.loads(line)
        print(json.dumps(data))
    print(json.dumps({"type": "assistant", "message": {"model": "test", "content": [{"type": "text", "text": f"Response {i}"}]}}))
    print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()

            # Send multiple messages
            for i in range(3):
                client.message_handler._query_complete_event = threading.Event()
                test_msg = {"seq": i, "text": f"message{i}"}
                client._manager.write_request(test_msg)
                time.sleep(0.2)  # Wait for processing

            messages = client.message_handler.get_messages()
            # Should have 6 messages (3 assistant + 3 result)
            assert len(messages) >= 6

        finally:
            client.disconnect()

    def test_session_id_persists_across_queries(self):
        """Test that session_id remains constant across multiple queries."""
        options = ClaudeOptions()
        handler = DefaultMessageHandler()
        client = ClaudeClient(options=options, message_handler=handler)
        session_id = client.session_id

        client._build_command = lambda: get_cat_command()

        try:
            client.connect()

            # Query 1
            client.message_handler._query_complete_event = threading.Event()
            client._manager.write_request({"q": 1})
            time.sleep(0.1)

            # Query 2
            client.message_handler._query_complete_event = threading.Event()
            client._manager.write_request({"q": 2})
            time.sleep(0.1)

            # Session ID should be unchanged
            assert client.session_id == session_id

        finally:
            client.disconnect()

    def test_interrupt_signal(self):
        """Test sending interrupt signal."""
        options = ClaudeOptions()
        handler = DefaultMessageHandler()
        client = ClaudeClient(options=options, message_handler=handler)
        client._build_command = lambda: get_cat_command()

        try:
            client.connect()
            client.interrupt()

            # The interrupt was sent successfully
            assert client.is_connected

        finally:
            client.disconnect()


class TestClaudeClientMessageHandling:
    """Test message parsing and handling in real scenarios."""

    def test_parse_assistant_message_from_script(self):
        """Test parsing assistant messages using echo script."""
        options = ClaudeOptions()
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script to output messages
        script = """
import sys, json
print(json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-4-5", "content": [{"type": "text", "text": "Hello, world!"}, {"type": "thinking", "thinking": "Let me think...", "signature": "sig"}]}}))
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test-session"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()

            # Send a dummy message to trigger the script
            client._manager.write_request({"trigger": "start"})

            # Wait for listener to capture all messages
            time.sleep(0.5)

            messages = client.message_handler.get_messages()

            # Should get back assistant and result messages
            assert len(messages) >= 2
            assert isinstance(messages[0], AssistantMessage)
            assert len(messages[0].content) == 2
            assert isinstance(messages[0].content[0], TextBlock)
            assert messages[0].content[0].text == "Hello, world!"

        finally:
            client.disconnect()

    def test_handle_malformed_json_gracefully(self):
        """Test that malformed JSON is handled gracefully by the listener."""
        import os
        import tempfile

        # Create a temporary file with mixed valid/invalid JSON
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".txt", encoding="utf-8"
        ) as f:
            temp_file = f.name
            f.write('{"type": "assistant", "message": {"model": "sonnet", "content": []}}\n')
            f.write("invalid json line\n")
            f.write(
                '{"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": false, "num_turns": 1, "session_id": "test"}\n'
            )

        try:
            options = ClaudeOptions()

            # Custom handler to track errors
            class TrackingHandler(MessageEventListener):
                def __init__(self):
                    self.messages = []
                    self.errors = []

                def on_message(self, message):
                    self.messages.append(message)

                def on_error(self, error):
                    self.errors.append(error)

            handler = TrackingHandler()
            client = ClaudeClient(options=options, message_handler=handler)

            # Use Python script to output the file content once (cross-platform)
            script = f"""
import sys
with open(r"{temp_file}", "r", encoding="utf-8") as f:
    for line in f:
        print(line, end="")
"""
            client._build_command = lambda: [sys.executable, "-c", script]

            client.connect()

            # Send trigger to start
            client._manager.write_request({"start": True})

            # Wait for listener to process all messages
            time.sleep(0.5)

            # Should get 2 valid messages (assistant + result)
            # Malformed JSON should be skipped and error logged
            assert len(handler.messages) == 2, f"Expected 2 messages, got {len(handler.messages)}"
            assert isinstance(handler.messages[0], AssistantMessage)
            assert isinstance(handler.messages[1], ResultMessage)

            # Should have captured the parse error
            assert len(handler.errors) > 0

            client.disconnect()

        finally:
            os.unlink(temp_file)


class TestClaudeClientErrorScenarios:
    """Test error handling and edge cases."""

    def test_process_during_query(self):
        """Test behavior when process exits during query."""
        options = ClaudeOptions()
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python command that reads one line then exits
        script = 'import sys; line = sys.stdin.readline(); print(line if line else "")'
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()
            client._manager.write_request({"test": "data"})

            # Wait for listener to process
            time.sleep(0.2)

            # Process should have exited
            assert not client.is_connected

        finally:
            client.disconnect()

    def test_query_after_reconnect(self):
        """Test that client can be reused after disconnect."""
        options = ClaudeOptions()

        handler1 = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler1, options=options)

        # Use Python script that echoes a result message
        script = """
import sys, json
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            # First session
            client.connect()
            client._manager.write_request({"session": 1})
            time.sleep(0.3)
            messages1 = client.message_handler.get_messages()
            len(messages1)
            client.disconnect()

            # Wait a bit for cleanup
            time.sleep(0.1)

            # Second session - create new client to simulate fresh start
            handler2 = DefaultMessageHandler()
            client2 = ClaudeClient(message_handler=handler2, options=options)
            client2._build_command = lambda: [sys.executable, "-c", script]
            client2.connect()
            client2.message_handler._query_complete_event = threading.Event()
            client2._manager.write_request({"session": 2})
            time.sleep(0.3)

            messages2 = client2.message_handler.get_messages()
            assert len(messages2) >= 1

            client2.disconnect()

        finally:
            client.disconnect()


class TestClaudeClientContextManager:
    """Test context manager behavior."""

    def test_context_manager_cleanup_on_error(self):
        """Test that context manager cleans up even on error."""
        options = ClaudeOptions()
        handler = DefaultMessageHandler()
        client = ClaudeClient(options=options, message_handler=handler)
        client._build_command = lambda: get_cat_command()

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

        handler1 = DefaultMessageHandler()
        handler2 = DefaultMessageHandler()
        client1 = ClaudeClient(options=options1, message_handler=handler1)
        client2 = ClaudeClient(options=options2, message_handler=handler2)

        client1._build_command = lambda: get_cat_command()
        client2._build_command = lambda: get_cat_command()

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
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script to write to stderr
        script = """
import sys, json
sys.stderr.write("stderr message\\n")
sys.stderr.flush()
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()

            # Send trigger
            client._manager.write_request({"start": True})

            # Wait for processing
            time.sleep(0.3)

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
        handler = DefaultMessageHandler()
        client = ClaudeClient(options=options, message_handler=handler)
        client._build_command = lambda: get_cat_command()

        # Create a large message
        large_text = "x" * 10000
        large_message = {
            "type": "assistant",
            "message": {"model": "sonnet", "content": [{"type": "text", "text": large_text}]},
        }

        try:
            client.connect()
            client._manager.write_request(large_message)

            # Wait for listener
            time.sleep(0.2)

            messages = client.message_handler.get_messages()
            assert len(messages) >= 1

        finally:
            client.disconnect()

    def test_multiple_messages_in_sequence(self):
        """Test sending many messages in sequence."""
        options = ClaudeOptions()

        # Use Python script with a loop that outputs 10 messages
        handler = DefaultMessageHandler()
        script = """
import sys, json
for i in range(1, 11):
    line = sys.stdin.readline()
    if line:
        data = json.loads(line)
        print(json.dumps(data))
    print(json.dumps({"type": "assistant", "message": {"model": "test", "content": [{"type": "text", "text": f"Message {i}"}]}}))
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 10, "session_id": "test"}))
"""
        client = ClaudeClient(message_handler=handler, options=options)
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()

            # Send 10 messages
            for i in range(10):
                msg = {"index": i}
                client._manager.write_request(msg)
                time.sleep(0.02)  # Small delay between sends

            # Wait for processing
            time.sleep(0.5)

            messages = client.message_handler.get_messages()
            # Should have 11 messages (10 assistant + 1 result)
            assert len(messages) >= 11

        finally:
            client.disconnect()


class TestClaudeClientTimeouts:
    """Test timeout handling."""

    def test_read_timeout_with_alive_process(self):
        """Test that timeout works correctly."""
        import sys

        options = ClaudeOptions()
        handler = DefaultMessageHandler()
        client = ClaudeClient(options=options, message_handler=handler)

        # Use Python script that sleeps then exits
        client._build_command = lambda: [sys.executable, "-c", "import time; time.sleep(0.1)"]

        try:
            client.connect()

            # Wait for process to exit
            time.sleep(0.3)

            # Process should have exited
            assert not client.is_connected

        finally:
            client.disconnect()


class TestAsyncClaudeClientRealSubprocess:
    """Integration tests for AsyncClaudeClient using real subprocess commands."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_cat(self):
        """Test full connect/query/disconnect lifecycle."""
        options = ClaudeOptions()
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler, options=options)

        # Use Python script to output messages
        script = """
import sys, json
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            # Connect
            await client.connect()
            assert client.is_connected

            # Send a message
            test_message = {"test": "data", "content": "hello"}
            await client._manager.write_request(test_message)

            # Wait for listener
            await asyncio.sleep(0.3)

            messages = client.message_handler.get_messages()
            assert len(messages) >= 1

        finally:
            await client.disconnect()
            assert not client.is_connected

    @pytest.mark.asyncio
    async def test_multiple_queries_in_session(self):
        """Test multiple queries within the same session."""
        options = ClaudeOptions()

        # Use Python script with a loop that outputs 3 responses
        handler = AsyncDefaultMessageHandler()
        script = """
import sys, json
for i in range(1, 4):
    line = sys.stdin.readline()
    if line:
        data = json.loads(line)
        print(json.dumps(data))
    print(json.dumps({"type": "assistant", "message": {"model": "test", "content": [{"type": "text", "text": f"Response {i}"}]}}))
    print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client = AsyncClaudeClient(message_handler=handler, options=options)
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            await client.connect()

            # Send multiple messages
            for i in range(3):
                await client._manager.write_request({"seq": i})
                await asyncio.sleep(0.15)

            messages = await client.message_handler.get_messages()
            # Should have 6 messages (3 assistant + 3 result)
            assert len(messages) >= 6

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager behavior."""
        options = ClaudeOptions()
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(options=options, message_handler=handler)
        client._build_command = lambda: get_cat_command()

        async with client:
            assert client.is_connected
            await client._manager.write_request({"test": "data"})
            await asyncio.sleep(0.1)

        # Should be disconnected after context
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_async_interrupt(self):
        """Test async interrupt functionality."""
        options = ClaudeOptions()
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(options=options, message_handler=handler)
        client._build_command = lambda: get_cat_command()

        try:
            await client.connect()
            await client.interrupt()

            # The interrupt was sent successfully
            assert client.is_connected

        finally:
            await client.disconnect()


class TestClientComparison:
    """Compare sync and async client behavior."""

    def test_sync_async_equivalent_session_id_generation(self):
        """Test that sync and async clients generate session IDs the same way."""
        options = ClaudeOptions()

        sync_client = ClaudeClient(options=options, message_handler=DefaultMessageHandler())
        async_client = AsyncClaudeClient(
            options=ClaudeOptions(), message_handler=DefaultMessageHandler()
        )

        # Both should generate valid UUIDs
        import uuid

        uuid.UUID(sync_client.session_id)
        uuid.UUID(async_client.session_id)

        # Should be different (random)
        assert sync_client.session_id != async_client.session_id

    @pytest.mark.asyncio
    async def test_sync_async_same_command_building(self):
        """Test that sync and async build commands the same way."""
        session_id = "test-session-123"
        options = ClaudeOptions(model="sonnet", session_id=session_id)

        sync_client = ClaudeClient(options=options, message_handler=DefaultMessageHandler())
        async_client = AsyncClaudeClient(
            options=ClaudeOptions(model="sonnet", session_id=session_id),
            message_handler=DefaultMessageHandler(),
        )

        sync_cmd = sync_client._build_command()
        async_cmd = async_client._build_command()

        assert sync_cmd == async_cmd
        assert "--model" in sync_cmd
        assert "sonnet" in sync_cmd


class TestMessageHandlerIntegration:
    """Test message handler integration with clients."""

    def test_custom_handler_receives_messages(self):
        """Test that custom handler receives all messages."""
        options = ClaudeOptions()

        class CustomHandler(MessageEventListener):
            def __init__(self):
                self.received = []

            def on_message(self, message):
                self.received.append(message)

            def on_query_complete(self, messages):
                self.received.append(("complete", len(messages)))

        handler = CustomHandler()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script to output messages
        script = """
import sys, json
print(json.dumps({"type": "assistant", "message": {"model": "test", "content": [{"type": "text", "text": "Hi"}]}}))
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()
            client._manager.write_request({"start": True})
            time.sleep(0.3)

            # Handler should have received messages and completion event
            assert len(handler.received) >= 3  # 2 messages + 1 complete event

        finally:
            client.disconnect()

    @pytest.mark.asyncio
    async def test_async_handler_receives_messages(self):
        """Test that async handler receives all messages."""
        options = ClaudeOptions()

        handler = AsyncDefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler, options=options)

        # Use Python script to output messages
        script = """
import sys, json
print(json.dumps({"type": "assistant", "message": {"model": "test", "content": [{"type": "text", "text": "Hi"}]}}))
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            await client.connect()
            await client._manager.write_request({"start": True})
            await asyncio.sleep(0.3)

            messages = await handler.get_messages()
            assert len(messages) >= 2

        finally:
            await client.disconnect()
