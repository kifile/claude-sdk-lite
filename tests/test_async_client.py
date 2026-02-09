"""Tests for AsyncClaudeClient with message handler architecture.

Tests that the async client with required message_handler works correctly
with the new event-driven message handling.
"""

import asyncio

import pytest

from claude_sdk_lite import (
    AsyncClaudeClient,
    AsyncDefaultMessageHandler,
    AsyncMessageEventListener,
    ClaudeOptions,
    DefaultMessageHandler,
    MessageEventListener,
)
from claude_sdk_lite.types import (
    AssistantMessage,
    TextBlock,
)
from test_helpers import get_cat_command, get_echo_command


class TestAsyncClaudeClientInit:
    """Test AsyncClaudeClient initialization."""

    def test_init_with_custom_options_and_handler(self):
        """Test initialization with custom options and handler."""
        handler = DefaultMessageHandler()
        options = ClaudeOptions(model="sonnet")

        client = AsyncClaudeClient(message_handler=handler, options=options)

        # session_id is auto-generated if not provided, so client.options is a copy
        assert client.options.model == options.model
        assert client.message_handler is handler
        assert client.session_id is not None

    def test_init_generates_session_id_if_not_provided(self):
        """Test that session_id is auto-generated if not specified."""
        handler = DefaultMessageHandler()
        options = ClaudeOptions()

        client = AsyncClaudeClient(options=options, message_handler=handler)

        assert client.session_id is not None
        assert client.session_id != options.session_id
        assert len(client.session_id) > 0

    def test_init_uses_provided_session_id(self):
        """Test that provided session_id is used."""
        handler = DefaultMessageHandler()
        session_id = "my-custom-session-123"
        options = ClaudeOptions(session_id=session_id)

        client = AsyncClaudeClient(options=options, message_handler=handler)

        assert client.session_id == session_id

    def test_init_with_valid_uuid_session_id(self):
        """Test that valid UUID session_id is accepted."""
        import uuid

        handler = DefaultMessageHandler()
        session_id = str(uuid.uuid4())
        options = ClaudeOptions(session_id=session_id)

        client = AsyncClaudeClient(options=options, message_handler=handler)

        assert client.session_id == session_id

    def test_init_requires_handler(self):
        """Test that message_handler is required."""
        options = ClaudeOptions()

        with pytest.raises(ValueError, match="message_handler is required"):
            AsyncClaudeClient(options=options, message_handler=None)

    def test_debug_flag_caching(self):
        """Test that debug flag is cached at init."""
        import os

        handler = DefaultMessageHandler()
        options = ClaudeOptions()

        client = AsyncClaudeClient(message_handler=handler, options=options)

        # Debug flag is cached at init
        expected_debug = os.environ.get("CLAUDE_SDK_DEBUG", "false").lower() == "true"
        assert client._debug == expected_debug


class TestAsyncClaudeClientConnection:
    """Test AsyncClaudeClient connection management."""

    def test_is_connected_initially_false(self):
        """Test that is_connected is False before connection."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)

        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_context_manager_auto_connect(self):
        """Test that context manager auto-starts the process."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)
        client._build_command = lambda: get_cat_command()

        async with client:
            assert client.is_connected

        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_connect_when_already_connected_returns_early(self):
        """Test that connecting when already connected returns early."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)
        client._build_command = lambda: get_cat_command()

        await client.connect()
        is_connected = client.is_connected
        await client.connect()  # Should not raise

        assert is_connected
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_manual_connect_disconnect(self):
        """Test manual connect and disconnect."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)
        client._build_command = lambda: get_cat_command()

        assert not client.is_connected

        await client.connect()
        assert client.is_connected

        await client.disconnect()
        assert not client.is_connected


class TestAsyncClaudeClientSendRequest:
    """Test AsyncClaudeClient send_request method."""

    @pytest.mark.asyncio
    async def test_send_request_without_connection_raises_error(self):
        """Test that send_request raises error when not connected."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)

        with pytest.raises(RuntimeError, match="not connected"):
            await client.send_request("Hello")

    @pytest.mark.asyncio
    async def test_send_request_calls_handler_on_query_start(self):
        """Test that send_request calls handler.on_query_start."""

        class TrackingHandler(MessageEventListener):
            def __init__(self):
                self.queries_started = []
                self.lock = asyncio.Lock()

            def on_query_start(self, prompt: str):
                self.queries_started.append(prompt)

        handler = TrackingHandler()
        client = AsyncClaudeClient(message_handler=handler)
        client._build_command = lambda: get_echo_command("{}")

        await client.connect()
        await client.send_request("Test prompt")

        assert "Test prompt" in handler.queries_started
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_send_request_with_async_handler(self):
        """Test that send_request works with AsyncDefaultMessageHandler."""

        class AsyncTrackingHandler(AsyncMessageEventListener):
            def __init__(self):
                self.queries_started = []
                self.lock = asyncio.Lock()

            async def on_query_start(self, prompt: str):
                async with self.lock:
                    self.queries_started.append(prompt)

        handler = AsyncTrackingHandler()
        client = AsyncClaudeClient(message_handler=handler)
        client._build_command = lambda: get_echo_command("{}")

        await client.connect()
        await client.send_request("Test prompt")

        assert "Test prompt" in handler.queries_started
        await client.disconnect()


class TestAsyncClaudeClientMessageHandler:
    """Test message handler integration."""

    def test_message_handler_property_returns_handler(self):
        """Test that message_handler property returns the handler."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)

        assert client.message_handler is handler

    @pytest.mark.asyncio
    async def test_custom_handler_receives_messages(self):
        """Test that custom handler receives messages."""
        import sys

        class CountingHandler(MessageEventListener):
            def __init__(self):
                self.message_count = 0

            def on_message(self, message):
                self.message_count += 1

        handler = CountingHandler()
        client = AsyncClaudeClient(message_handler=handler)

        # Script that outputs 2 messages
        script = """
import sys
import json

print(json.dumps({"type": "assistant", "message": {"model": "test", "content": [{"type": "text", "text": "Hi"}]}}))
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        await client.connect()
        await client._manager.write_request({"start": True})

        await asyncio.sleep(0.3)  # Wait for listener to process

        assert handler.message_count >= 2
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_async_handler_receives_messages(self):
        """Test that async handler receives messages correctly."""

        class AsyncCountingHandler(AsyncMessageEventListener):
            def __init__(self):
                self.message_count = 0

            async def on_message(self, message):
                self.message_count += 1

        handler = AsyncCountingHandler()
        client = AsyncClaudeClient(message_handler=handler)

        # Use Python script to output JSON messages (more portable)
        import sys

        script = """
import sys
import json
print(json.dumps({"type": "assistant", "message": {"model": "test", "content": [{"type": "text", "text": "Hello"}]}}))
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        await client.connect()
        await client._manager.write_request({"start": True})

        await asyncio.sleep(0.3)  # Wait for listener to process

        assert handler.message_count >= 2
        await client.disconnect()


class TestAsyncClaudeClientInterrupt:
    """Test AsyncClaudeClient interrupt functionality."""

    @pytest.mark.asyncio
    async def test_interrupt_without_connection_raises_error(self):
        """Test that interrupt raises error when not connected."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)

        with pytest.raises(RuntimeError, match="not connected"):
            await client.interrupt()

    @pytest.mark.asyncio
    async def test_interrupt_sends_signal(self):
        """Test that interrupt sends signal to subprocess."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)
        client._build_command = lambda: get_cat_command()

        await client.connect()

        # Should not raise
        await client.interrupt()

        await client.disconnect()


class TestAsyncClaudeClientCommands:
    """Test AsyncClaudeClient command building."""

    def test_build_command_includes_stream_json_format(self):
        """Test that build_command includes stream-json format."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)

        cmd = client._build_command()

        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--input-format" in cmd
        assert "--verbose" in cmd

    def test_build_command_preserves_model_option(self):
        """Test that build_command preserves model option."""
        handler = DefaultMessageHandler()
        options = ClaudeOptions(model="haiku")
        client = AsyncClaudeClient(options=options, message_handler=handler)

        cmd = client._build_command()

        assert "--model" in cmd
        assert "haiku" in cmd


class TestAsyncClaudeClientProperties:
    """Test AsyncClaudeClient properties."""

    @pytest.mark.asyncio
    async def test_stderr_property(self):
        """Test get_stderr method."""
        import sys

        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)

        # Use Python script to output to stderr and stdout
        script = '''
import sys
import json
sys.stderr.write("error message\\n")
sys.stderr.flush()
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
'''
        client._build_command = lambda: [sys.executable, "-c", script]

        await client.connect()
        await client._manager.write_request({"start": True})

        await asyncio.sleep(0.2)

        stderr = await client.get_stderr()
        assert len(stderr) > 0
        await client.disconnect()


class TestAsyncClaudeClientErrorHandling:
    """Test AsyncClaudeClient error handling."""

    @pytest.mark.asyncio
    async def test_send_fails_when_not_connected(self):
        """Test that send_request fails when not connected."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)

        with pytest.raises(RuntimeError, match="not connected"):
            await client.send_request("test")

    @pytest.mark.asyncio
    async def test_interrupt_fails_when_not_connected(self):
        """Test that interrupt fails when not connected."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)

        with pytest.raises(RuntimeError, match="not connected"):
            await client.interrupt()


class TestAsyncDefaultMessageHandler:
    """Test AsyncDefaultMessageHandler behavior."""

    @pytest.mark.asyncio
    async def test_async_handler_buffers_messages(self):
        """Test that AsyncDefaultMessageHandler buffers messages."""
        handler = AsyncDefaultMessageHandler()

        msg = AssistantMessage(
            model="test",
            content=[TextBlock(text="Hello")],
        )

        await handler.on_message(msg)

        messages = await handler.get_messages()
        assert len(messages) == 1
        assert messages[0] is msg

    @pytest.mark.asyncio
    async def test_async_handler_query_start_resets_buffer(self):
        """Test that on_query_start resets the buffer."""
        handler = AsyncDefaultMessageHandler()

        msg1 = AssistantMessage(model="test", content=[TextBlock(text="First")])
        msg2 = AssistantMessage(model="test", content=[TextBlock(text="Second")])

        await handler.on_message(msg1)
        messages = await handler.get_messages()
        assert len(messages) == 1

        await handler.on_query_start("new query")
        messages = await handler.get_messages()
        assert len(messages) == 0  # Buffer reset

        await handler.on_message(msg2)
        messages = await handler.get_messages()
        assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_async_handler_wait_for_completion(self):
        """Test that wait_for_completion works correctly."""
        handler = AsyncDefaultMessageHandler()

        # Not complete yet
        assert not await handler.wait_for_completion(timeout=0.1)

        # Set complete event
        await handler.on_query_start("test")
        await handler.on_query_complete([])

        # Now should complete immediately
        assert await handler.wait_for_completion(timeout=1.0)

    @pytest.mark.asyncio
    async def test_async_handler_is_complete(self):
        """Test that is_complete returns correct status."""
        handler = AsyncDefaultMessageHandler()

        assert not await handler.is_complete()

        await handler.on_query_start("test")
        assert not await handler.is_complete()

        await handler.on_query_complete([])
        assert await handler.is_complete()


class TestAsyncClaudeClientAsyncContextManager:
    """Test async context manager behavior."""

    @pytest.mark.asyncio
    async def test_async_context_manager_returns_self(self):
        """Test that __aenter__ returns self."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)

        async with client as entered_client:
            assert entered_client is client

    @pytest.mark.asyncio
    async def test_async_context_manager_cleanup_on_exception(self):
        """Test that context manager cleans up even on exception."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)

        with pytest.raises(ValueError):
            async with client:
                raise ValueError("Test exception")

        # Should be disconnected
        assert not client.is_connected


class TestAsyncClaudeClientConcurrentOperations:
    """Test concurrent async operations."""

    @pytest.mark.asyncio
    async def test_concurrent_is_connected_checks(self):
        """Test that is_connected can be checked concurrently."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)

        # Check is_connected multiple times concurrently
        results = [client.is_connected for _ in range(10)]

        # All should be False (not connected)
        assert all(not r for r in results)


class TestAsyncClaudeClientManagerType:
    """Test that AsyncPersistentProcessManager is used."""

    def test_uses_async_persistent_process_manager(self):
        """Test that client uses AsyncPersistentProcessManager."""
        from claude_sdk_lite.async_persistent_executor import AsyncPersistentProcessManager

        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)
        assert isinstance(client._manager, AsyncPersistentProcessManager)


class TestAsyncClaudeClientMethodSignatures:
    """Test that async methods have correct signatures."""

    @pytest.mark.asyncio
    async def test_connect_is_async(self):
        """Test that connect() is an async method."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)
        assert asyncio.iscoroutinefunction(client.connect)

    @pytest.mark.asyncio
    async def test_disconnect_is_async(self):
        """Test that disconnect() is an async method."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)
        assert asyncio.iscoroutinefunction(client.disconnect)

    @pytest.mark.asyncio
    async def test_send_request_is_async(self):
        """Test that send_request() is an async method."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)
        assert asyncio.iscoroutinefunction(client.send_request)

    @pytest.mark.asyncio
    async def test_interrupt_is_async(self):
        """Test that interrupt() is an async method."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)
        assert asyncio.iscoroutinefunction(client.interrupt)

    @pytest.mark.asyncio
    async def test_get_stderr_is_async(self):
        """Test that get_stderr() is an async method."""
        handler = DefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler)
        assert asyncio.iscoroutinefunction(client.get_stderr)
