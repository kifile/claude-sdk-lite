"""Tests for ClaudeClient with message handler architecture.

Tests that the client with required message_handler works correctly
with the new event-driven message handling.
"""

import pytest
from test_helpers import get_cat_command, get_echo_command

from claude_sdk_lite import (
    ClaudeClient,
    ClaudeOptions,
    DefaultMessageHandler,
    MessageEventListener,
)


class TestClaudeClientInit:
    """Test ClaudeClient initialization."""

    def test_init_with_custom_options_and_handler(self):
        """Test initialization with custom options and handler."""
        handler = DefaultMessageHandler()
        options = ClaudeOptions(model="sonnet")

        client = ClaudeClient(message_handler=handler, options=options)

        # session_id is auto-generated if not provided, so client.options is a copy
        assert client.options.model == options.model
        assert client.message_handler is handler
        assert client.session_id is not None

    def test_init_generates_session_id_if_not_provided(self):
        """Test that session_id is auto-generated if not specified."""
        handler = DefaultMessageHandler()
        options = ClaudeOptions()

        client = ClaudeClient(options=options, message_handler=handler)

        assert client.session_id is not None
        assert client.session_id != options.session_id
        assert len(client.session_id) > 0

    def test_init_uses_provided_session_id(self):
        """Test that provided session_id is used."""
        handler = DefaultMessageHandler()
        session_id = "my-custom-session-123"
        options = ClaudeOptions(session_id=session_id)

        client = ClaudeClient(options=options, message_handler=handler)

        assert client.session_id == session_id

    def test_init_with_valid_uuid_session_id(self):
        """Test that valid UUID session_id is accepted."""
        import uuid

        handler = DefaultMessageHandler()
        session_id = str(uuid.uuid4())
        options = ClaudeOptions(session_id=session_id)

        client = ClaudeClient(options=options, message_handler=handler)

        assert client.session_id == session_id

    def test_init_requires_handler(self):
        """Test that message_handler is required."""
        options = ClaudeOptions()

        with pytest.raises(ValueError, match="message_handler is required"):
            ClaudeClient(options=options, message_handler=None)

    def test_debug_flag_caching(self):
        """Test that debug flag is cached at init."""
        import os

        handler = DefaultMessageHandler()
        options = ClaudeOptions()

        client = ClaudeClient(message_handler=handler, options=options)

        # Debug flag is cached at init
        expected_debug = os.environ.get("CLAUDE_SDK_DEBUG", "false").lower() == "true"
        assert client._debug == expected_debug


class TestClaudeClientConnection:
    """Test ClaudeClient connection management."""

    def test_is_connected_initially_false(self):
        """Test that is_connected is False before connection."""
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)

        assert not client.is_connected

    def test_context_manager_auto_connect(self):
        """Test that context manager auto-starts the process."""
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)
        client._build_command = lambda: get_cat_command()

        with client:
            assert client.is_connected

        assert not client.is_connected

    def test_connect_when_already_connected_returns_early(self):
        """Test that connecting when already connected returns early."""
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)
        client._build_command = lambda: get_cat_command()

        client.connect()
        is_connected = client.is_connected
        client.connect()  # Should not raise

        assert is_connected
        client.disconnect()

    def test_manual_connect_disconnect(self):
        """Test manual connect and disconnect."""
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)
        client._build_command = lambda: get_cat_command()

        assert not client.is_connected

        client.connect()
        assert client.is_connected

        client.disconnect()
        assert not client.is_connected


class TestClaudeClientSendRequest:
    """Test ClaudeClient send_request method."""

    def test_send_request_without_connection_raises_error(self):
        """Test that send_request raises error when not connected."""
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)

        with pytest.raises(RuntimeError, match="not connected"):
            client.send_request("Hello")

    def test_send_request_calls_handler_on_query_start(self):
        """Test that send_request calls handler.on_query_start."""

        class TrackingHandler(MessageEventListener):
            def __init__(self):
                self.queries_started = []

            def on_query_start(self, prompt: str):
                self.queries_started.append(prompt)

        handler = TrackingHandler()
        client = ClaudeClient(message_handler=handler)
        client._build_command = lambda: get_echo_command("{}")

        client.connect()
        client.send_request("Test prompt")

        assert "Test prompt" in handler.queries_started
        client.disconnect()


class TestClaudeClientMessageHandler:
    """Test message handler integration."""

    def test_message_handler_property_returns_handler(self):
        """Test that message_handler property returns the handler."""
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)

        assert client.message_handler is handler

    def test_custom_handler_receives_messages(self):
        """Test that custom handler receives messages."""

        class CountingHandler(MessageEventListener):
            def __init__(self):
                self.message_count = 0

            def on_message(self, message):
                self.message_count += 1

        handler = CountingHandler()
        client = ClaudeClient(message_handler=handler)

        # Use Python script to output JSON messages (more portable than shell)
        import sys

        script = """
import sys
import json
print(json.dumps({"type": "assistant", "message": {"model": "test", "content": [{"type": "text", "text": "Hi"}]}}))
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        client.connect()
        client._manager.write_request({"start": True})

        import time

        time.sleep(0.3)  # Wait for listener to process

        assert handler.message_count >= 2
        client.disconnect()


class TestClaudeClientInterrupt:
    """Test ClaudeClient interrupt functionality."""

    def test_interrupt_without_connection_raises_error(self):
        """Test that interrupt raises error when not connected."""
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)

        with pytest.raises(RuntimeError, match="not connected"):
            client.interrupt()

    def test_interrupt_sends_signal(self):
        """Test that interrupt sends signal to subprocess."""
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)
        client._build_command = lambda: get_cat_command()

        client.connect()

        # Should not raise
        client.interrupt()

        client.disconnect()


class TestClaudeClientCommands:
    """Test ClaudeClient command building."""

    def test_build_command_includes_stream_json_format(self):
        """Test that build_command includes stream-json format."""
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)

        cmd = client._build_command()

        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--input-format" in cmd
        assert "--verbose" in cmd

    def test_build_command_preserves_model_option(self):
        """Test that build_command preserves model option."""
        handler = DefaultMessageHandler()
        options = ClaudeOptions(model="haiku")
        client = ClaudeClient(options=options, message_handler=handler)

        cmd = client._build_command()

        assert "--model" in cmd
        assert "haiku" in cmd


class TestClaudeClientProperties:
    """Test ClaudeClient properties."""

    def test_stderr_property(self):
        """Test stderr_output property."""
        import sys

        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)

        # Use Python script to output to stderr and stdout
        script = """
import sys
import json
sys.stderr.write("error message\\n")
sys.stderr.flush()
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        client.connect()
        client._manager.write_request({"start": True})

        import time

        time.sleep(0.2)

        stderr = client.stderr_output
        assert len(stderr) > 0
        client.disconnect()


class TestClaudeClientErrorHandling:
    """Test ClaudeClient error handling."""

    def test_send_fails_when_not_connected(self):
        """Test that send_request fails when not connected."""
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)

        with pytest.raises(RuntimeError, match="not connected"):
            client.send_request("test")

    def test_interrupt_fails_when_not_connected(self):
        """Test that interrupt fails when not connected."""
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler)

        with pytest.raises(RuntimeError, match="not connected"):
            client.interrupt()


class TestDefaultMessageHandler:
    """Test DefaultMessageHandler behavior."""

    def test_default_handler_buffers_messages(self):
        """Test that DefaultMessageHandler buffers messages."""
        handler = DefaultMessageHandler()

        from claude_sdk_lite.types import AssistantMessage, TextBlock

        msg = AssistantMessage(
            model="test",
            content=[TextBlock(text="Hello")],
        )

        handler.on_message(msg)

        messages = handler.get_messages()
        assert len(messages) == 1
        assert messages[0] is msg

    def test_default_handler_query_start_resets_buffer(self):
        """Test that on_query_start resets the buffer."""
        handler = DefaultMessageHandler()

        from claude_sdk_lite.types import AssistantMessage, TextBlock

        msg1 = AssistantMessage(model="test", content=[TextBlock(text="First")])
        msg2 = AssistantMessage(model="test", content=[TextBlock(text="Second")])

        handler.on_message(msg1)
        assert len(handler.get_messages()) == 1

        handler.on_query_start("new query")
        assert len(handler.get_messages()) == 0  # Buffer reset

        handler.on_message(msg2)
        assert len(handler.get_messages()) == 1

    def test_default_handler_wait_for_completion(self):
        """Test that wait_for_completion works correctly."""
        handler = DefaultMessageHandler()

        # Not complete yet
        assert not handler.wait_for_completion(timeout=0.1)

        # Set complete event
        handler.on_query_start("test")
        handler.on_query_complete([])

        # Now should complete immediately
        assert handler.wait_for_completion(timeout=1.0)

    def test_default_handler_is_complete(self):
        """Test that is_complete returns correct status."""
        handler = DefaultMessageHandler()

        assert not handler.is_complete()

        handler.on_query_start("test")
        assert not handler.is_complete()

        handler.on_query_complete([])
        assert handler.is_complete()
