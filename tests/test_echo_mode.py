"""Tests for echo mode functionality in ClaudeClient.

Echo mode allows user input and interrupt signals to be echoed back
through the on_message callback for display purposes.
"""

import asyncio
import sys
import threading
import time

import pytest

from claude_sdk_lite import (
    AsyncClaudeClient,
    AsyncDefaultMessageHandler,
    AsyncMessageEventListener,
    ClaudeClient,
    ClaudeOptions,
    DefaultMessageHandler,
    MessageEventListener,
)
from claude_sdk_lite.types import (
    InterruptBlock,
    TextBlock,
    UserMessage,
)

# =============================================================================
# Helper Classes for Reliable Testing
# =============================================================================


class SyncMessageCapture(MessageEventListener):
    """Message handler that captures messages with event-based synchronization.

    This helper class provides reliable message waiting without time.sleep()
    by using threading.Event for synchronization.
    """

    def __init__(self):
        self.messages = []
        self.query_started = False
        self.message_event = threading.Event()
        self.query_start_event = threading.Event()

    def on_message(self, message):
        self.messages.append(message)
        self.message_event.set()

    def on_query_start(self, _prompt):
        self.query_started = True
        self.query_start_event.set()

    def wait_for_message(self, timeout=1.0, min_count=1):
        """Wait for at least min_count messages to arrive.

        Returns:
            bool: True if enough messages arrived, False on timeout.
        """
        deadline = time.time() + timeout
        while len(self.messages) < min_count and time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            self.message_event.wait(timeout=min(0.05, remaining))
            self.message_event.clear()
        return len(self.messages) >= min_count

    def wait_for_query_start(self, timeout=1.0):
        """Wait for query_start callback to be called.

        Returns:
            bool: True if query started, False on timeout.
        """
        return self.query_start_event.wait(timeout=timeout)


class AsyncMessageCapture(AsyncMessageEventListener):
    """Async message handler that captures messages with event-based synchronization.

    This helper class provides reliable message waiting for async tests.
    """

    def __init__(self):
        self.messages = []
        self.query_started = False
        self.message_event = asyncio.Event()
        self.query_start_event = asyncio.Event()

    async def on_message(self, message):
        self.messages.append(message)
        self.message_event.set()

    async def on_query_start(self, _prompt):
        self.query_started = True
        self.query_start_event.set()

    async def wait_for_message(self, timeout=1.0, min_count=1):
        """Wait for at least min_count messages to arrive."""
        deadline = time.time() + timeout
        while len(self.messages) < min_count and time.time() < deadline:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(self.message_event.wait(), timeout=min(0.05, remaining))
                self.message_event.clear()
            except asyncio.TimeoutError:
                break
        return len(self.messages) >= min_count

    async def wait_for_query_start(self, timeout=1.0):
        """Wait for query_start callback to be called."""
        try:
            await asyncio.wait_for(self.query_start_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False


def is_user_echo_with_text(message, text):
    """Check if a message is a user echo with specific text.

    Helper function for cleaner assertions.
    """
    return (
        isinstance(message, UserMessage)
        and isinstance(message.content, list)
        and len(message.content) > 0
        and isinstance(message.content[0], TextBlock)
        and message.content[0].text == text
    )


def has_user_echo_with_text(messages, text):
    """Check if any message in the list is a user echo with specific text."""
    return any(is_user_echo_with_text(msg, text) for msg in messages)


class TestEchoModeSync:
    """Test echo mode functionality in synchronous client."""

    def test_echo_mode_options_default(self):
        """Test that echo mode is disabled by default."""
        options = ClaudeOptions()
        assert options.echo_mode is False

    def test_echo_mode_options_enabled(self):
        """Test that echo mode can be enabled."""
        options = ClaudeOptions(echo_mode=True)
        assert options.echo_mode is True

    def test_user_input_echo_with_enabled_mode(self):
        """Test that user input is echoed when echo mode is enabled."""
        options = ClaudeOptions(echo_mode=True)
        handler = SyncMessageCapture()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script that reads stdin and outputs result
        script = """
import sys, json
line = sys.stdin.readline()
if line:
    data = json.loads(line)
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()

            # Send a request
            client.send_request("Hello, Claude!")

            # Wait for echo to be processed
            assert handler.wait_for_message(
                timeout=1.0, min_count=1
            ), "Timeout waiting for user input echo"
            assert handler.wait_for_query_start(timeout=1.0), "Timeout waiting for query start"

            # Should have received user input echo
            assert len(handler.messages) >= 1
            assert isinstance(handler.messages[0], UserMessage)
            assert isinstance(handler.messages[0].content[0], TextBlock)
            assert handler.messages[0].content[0].text == "Hello, Claude!"
            assert handler.query_started is True

        finally:
            client.disconnect()

    def test_user_input_no_echo_with_disabled_mode(self):
        """Test that user input is NOT echoed when echo mode is disabled."""
        options = ClaudeOptions(echo_mode=False)
        handler = SyncMessageCapture()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script that only outputs result message
        script = """
import sys, json
line = sys.stdin.readline()
if line:
    data = json.loads(line)
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()

            # Send a request
            client.send_request("Hello, Claude!")

            # Wait for processing (result message should arrive)
            assert handler.wait_for_message(
                timeout=1.0, min_count=1
            ), "Timeout waiting for result message"
            assert handler.wait_for_query_start(timeout=1.0), "Timeout waiting for query start"

            # Should NOT have received user input echo
            assert not has_user_echo_with_text(
                handler.messages, "Hello, Claude!"
            ), "User echo should not appear when echo mode is disabled"
            assert handler.query_started is True

        finally:
            client.disconnect()

    def test_interrupt_signal_echo_with_enabled_mode(self):
        """Test that interrupt signal is echoed when echo mode is enabled."""
        options = ClaudeOptions(echo_mode=True)
        handler = SyncMessageCapture()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script that keeps running and reads stdin
        script = """
import sys, json
line = sys.stdin.readline()
if line:
    data = json.loads(line)
    # Keep running to allow interrupt
    while True:
        line = sys.stdin.readline()
        if not line:
            break
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()

            # Start a request first to set request_in_progress flag
            client.send_request("Test request")
            handler.wait_for_message(timeout=1.0, min_count=1)

            # Clear messages to isolate interrupt echo
            handler.messages.clear()
            if handler.message_event:
                handler.message_event.clear()

            # Send interrupt
            client.interrupt()

            # Wait for interrupt echo to be processed
            assert handler.wait_for_message(
                timeout=1.0, min_count=1
            ), "Timeout waiting for interrupt echo"

            # Should have received interrupt echo
            assert len(handler.messages) >= 1
            assert isinstance(handler.messages[0], UserMessage)
            assert isinstance(handler.messages[0].content[0], InterruptBlock)

        finally:
            client.disconnect()

    def test_interrupt_signal_no_echo_with_disabled_mode(self):
        """Test that interrupt signal is NOT echoed when echo mode is disabled."""
        options = ClaudeOptions(echo_mode=False)
        handler = SyncMessageCapture()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script that keeps running
        script = """
import sys, json
line = sys.stdin.readline()
if line:
    data = json.loads(line)
    # Keep running to allow interrupt
    while True:
        line = sys.stdin.readline()
        if not line:
            break
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()

            # Start a request first
            client.send_request("Test request")
            handler.wait_for_message(timeout=1.0, min_count=1)

            # Clear messages to isolate interrupt
            handler.messages.clear()
            if handler.message_event:
                handler.message_event.clear()

            # Send interrupt
            client.interrupt()

            # Give some time for processing (but don't expect any message)
            time.sleep(0.1)

            # Should NOT have received interrupt echo
            for msg in handler.messages:
                if isinstance(msg, UserMessage):
                    for block in msg.content if isinstance(msg.content, list) else []:
                        assert not isinstance(
                            block, InterruptBlock
                        ), "InterruptBlock should not appear when echo mode is disabled"

        finally:
            client.disconnect()

    def test_multiple_requests_with_echo(self):
        """Test multiple sequential requests with echo mode enabled."""
        options = ClaudeOptions(echo_mode=True)
        handler = SyncMessageCapture()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script that processes multiple requests
        script = """
import sys, json
for i in range(3):
    line = sys.stdin.readline()
    if line:
        data = json.loads(line)
        print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()

            # Send multiple requests
            requests = ["First", "Second", "Third"]
            for req in requests:
                handler.messages.clear()
                handler.message_event.clear()
                client.send_request(req)

                # Check that each request was echoed
                assert handler.wait_for_message(
                    timeout=1.0, min_count=1
                ), f"Timeout waiting for echo of request: {req}"
                assert len(handler.messages) >= 1
                assert isinstance(handler.messages[0], UserMessage)
                assert handler.messages[0].content[0].text == req

        finally:
            client.disconnect()


class TestEchoModeAsync:
    """Test echo mode functionality in asynchronous client."""

    @pytest.mark.asyncio
    async def test_async_user_input_echo_with_enabled_mode(self):
        """Test that user input is echoed in async client when echo mode is enabled."""
        options = ClaudeOptions(echo_mode=True)
        handler = AsyncMessageCapture()
        client = AsyncClaudeClient(message_handler=handler, options=options)

        # Use Python script that reads stdin and outputs result
        script = """
import sys, json
line = sys.stdin.readline()
if line:
    data = json.loads(line)
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            await client.connect()

            # Send a request
            await client.send_request("Hello, Async Claude!")

            # Wait for echo to be processed
            assert await handler.wait_for_message(
                timeout=1.0, min_count=1
            ), "Timeout waiting for user input echo"
            assert await handler.wait_for_query_start(
                timeout=1.0
            ), "Timeout waiting for query start"

            # Should have received user input echo
            assert len(handler.messages) >= 1
            assert isinstance(handler.messages[0], UserMessage)
            assert isinstance(handler.messages[0].content[0], TextBlock)
            assert handler.messages[0].content[0].text == "Hello, Async Claude!"
            assert handler.query_started is True

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_async_user_input_no_echo_with_disabled_mode(self):
        """Test that user input is NOT echoed in async client when echo mode is disabled."""
        options = ClaudeOptions(echo_mode=False)
        handler = AsyncMessageCapture()
        client = AsyncClaudeClient(message_handler=handler, options=options)

        # Use Python script that reads stdin and outputs result
        script = """
import sys, json
line = sys.stdin.readline()
if line:
    data = json.loads(line)
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            await client.connect()

            # Send a request
            await client.send_request("Hello, Async Claude!")

            # Wait for processing (result message should arrive)
            assert await handler.wait_for_message(
                timeout=1.0, min_count=1
            ), "Timeout waiting for result message"
            assert await handler.wait_for_query_start(
                timeout=1.0
            ), "Timeout waiting for query start"

            # Should NOT have received user input echo
            assert not has_user_echo_with_text(
                handler.messages, "Hello, Async Claude!"
            ), "User echo should not appear when echo mode is disabled"
            assert handler.query_started is True

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_async_interrupt_signal_echo_with_enabled_mode(self):
        """Test that interrupt signal is echoed in async client when echo mode is enabled."""
        options = ClaudeOptions(echo_mode=True)
        handler = AsyncMessageCapture()
        client = AsyncClaudeClient(message_handler=handler, options=options)

        # Use Python script that keeps running and reads stdin
        script = """
import sys, json
line = sys.stdin.readline()
if line:
    data = json.loads(line)
    # Keep running to allow interrupt
    while True:
        line = sys.stdin.readline()
        if not line:
            break
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            await client.connect()

            # Start a request first to set request_in_progress flag
            await client.send_request("Test request")
            await handler.wait_for_message(timeout=1.0, min_count=1)

            # Clear messages to isolate interrupt echo
            handler.messages.clear()
            if handler.message_event:
                handler.message_event.clear()

            # Send interrupt
            await client.interrupt()

            # Wait for interrupt echo to be processed
            assert await handler.wait_for_message(
                timeout=1.0, min_count=1
            ), "Timeout waiting for interrupt echo"

            # Should have received interrupt echo
            assert len(handler.messages) >= 1
            assert isinstance(handler.messages[0], UserMessage)
            assert isinstance(handler.messages[0].content[0], InterruptBlock)

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_async_multiple_requests_with_echo(self):
        """Test multiple sequential async requests with echo mode enabled."""
        options = ClaudeOptions(echo_mode=True)
        handler = AsyncMessageCapture()
        client = AsyncClaudeClient(message_handler=handler, options=options)

        # Use Python script that processes multiple requests
        script = """
import sys, json
for i in range(3):
    line = sys.stdin.readline()
    if line:
        data = json.loads(line)
        print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            await client.connect()

            # Send multiple requests
            requests = ["Async First", "Async Second", "Async Third"]
            for req in requests:
                handler.messages.clear()
                if handler.message_event:
                    handler.message_event.clear()
                await client.send_request(req)

                # Check that each request was echoed
                assert await handler.wait_for_message(
                    timeout=1.0, min_count=1
                ), f"Timeout waiting for echo of request: {req}"
                assert len(handler.messages) >= 1
                assert isinstance(handler.messages[0], UserMessage)
                assert handler.messages[0].content[0].text == req

        finally:
            await client.disconnect()


class TestEchoModeIntegration:
    """Integration tests for echo mode with message handlers."""

    def test_echo_with_default_message_handler(self):
        """Test that echo works with DefaultMessageHandler."""
        options = ClaudeOptions(echo_mode=True)
        handler = DefaultMessageHandler()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script that reads stdin and outputs result
        script = """
import sys, json
line = sys.stdin.readline()
if line:
    data = json.loads(line)
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()
            client.send_request("Test with default handler")

            # Wait for messages with timeout
            assert handler.wait_for_completion(timeout=1.0), "Timeout waiting for query completion"

            # Handler should buffer the echoed user message
            messages = handler.get_messages()
            assert len(messages) >= 1
            assert isinstance(messages[0], UserMessage)

        finally:
            client.disconnect()

    @pytest.mark.asyncio
    async def test_async_echo_with_default_message_handler(self):
        """Test that echo works with AsyncDefaultMessageHandler."""
        options = ClaudeOptions(echo_mode=True)
        handler = AsyncDefaultMessageHandler()
        client = AsyncClaudeClient(message_handler=handler, options=options)

        # Use Python script that reads stdin and outputs result
        script = """
import sys, json
line = sys.stdin.readline()
if line:
    data = json.loads(line)
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            await client.connect()
            await client.send_request("Test with async default handler")

            # Wait for messages with timeout
            assert await handler.wait_for_completion(
                timeout=1.0
            ), "Timeout waiting for query completion"

            # Handler should buffer the echoed user message
            messages = await handler.get_messages()
            assert len(messages) >= 1
            assert isinstance(messages[0], UserMessage)

        finally:
            await client.disconnect()

    def test_echo_timing_message_after_query_start(self):
        """Test that echoed user message comes after query start callback."""
        options = ClaudeOptions(echo_mode=True)

        class TimingHandler(MessageEventListener):
            def __init__(self):
                self.events = []
                self.message_event = threading.Event()

            def on_query_start(self, prompt):
                self.events.append(("query_start", prompt))

            def on_message(self, message):
                self.events.append(("message", type(message).__name__))
                self.message_event.set()

            def wait_for_messages(self, count, timeout=1.0):
                """Wait for at least count events."""
                deadline = time.time() + timeout
                while len(self.events) < count and time.time() < deadline:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        break
                    self.message_event.wait(timeout=min(0.05, remaining))
                    if self.message_event:
                        self.message_event.clear()
                return len(self.events) >= count

        handler = TimingHandler()
        client = ClaudeClient(message_handler=handler, options=options)

        # Use Python script that reads stdin and outputs result
        script = """
import sys, json
line = sys.stdin.readline()
if line:
    data = json.loads(line)
print(json.dumps({"type": "result", "subtype": "complete", "duration_ms": 100, "duration_api_ms": 50, "is_error": False, "num_turns": 1, "session_id": "test"}))
"""
        client._build_command = lambda: [sys.executable, "-c", script]

        try:
            client.connect()
            client.send_request("Timing test")

            # Wait for both events
            assert handler.wait_for_messages(
                2, timeout=1.0
            ), "Timeout waiting for query start and message events"

            # Query start should come before user message echo
            assert len(handler.events) >= 2
            assert handler.events[0][0] == "query_start"
            assert handler.events[1][0] == "message"
            assert handler.events[1][1] == "UserMessage"

        finally:
            client.disconnect()
