"""Message event listener for handling Claude SDK messages.

This module provides base classes for event-driven message handling,
allowing users to react to messages as they arrive without blocking.
"""

import asyncio
import logging
import threading

from .types import Message

logger = logging.getLogger(__name__)


class _MessageBufferMixin:
    """Shared message buffering logic for both sync and async handlers."""

    def _init_buffer(self) -> None:
        """Initialize message buffer state."""
        self._current_query_messages: list[Message] = []
        self._current_query_prompt: str | None = None
        self._streaming = False

    def _reset_buffer(self) -> None:
        """Reset buffer for new query."""
        self._current_query_messages = []
        self._current_query_prompt = None
        self._streaming = False


class MessageEventListener:
    """Base class for message event handlers.

    Implement this interface to create custom message handlers that react
    to messages as they arrive from the Claude Code CLI.

    Example:
        ```python
        class MyHandler(MessageEventListener):
            def on_message(self, message: Message):
                print(f"Received: {type(message).__name__}")

            def on_query_start(self, prompt: str):
                print(f"Query started: {prompt}")

            def on_query_complete(self, messages: list[Message]):
                print(f"Query complete with {len(messages)} messages")
        ```
    """

    def on_message(self, message: Message) -> None:
        """Called when any message is received."""

    def on_error(self, error: Exception) -> None:
        """Called when an error occurs."""

    def on_query_start(self, prompt: str) -> None:
        """Called when a query starts."""

    def on_query_complete(self, messages: list[Message]) -> None:
        """Called when a query completes."""

    def on_stream_start(self) -> None:
        """Called when streaming starts."""

    def on_stream_end(self) -> None:
        """Called when streaming ends."""


class DefaultMessageHandler(MessageEventListener, _MessageBufferMixin):
    """Default handler that buffers messages by query.

    This handler collects messages for each query and provides
    both synchronous and streaming access patterns.

    Thread-safe for use with background listener threads.
    """

    def __init__(self) -> None:
        """Initialize the default handler."""
        self._lock = threading.RLock()
        self._query_complete_event: threading.Event | None = None
        self._init_buffer()

    def on_message(self, message: Message) -> None:
        """Buffer message for current query."""
        with self._lock:
            self._current_query_messages.append(message)

    def on_query_start(self, prompt: str) -> None:
        """Initialize buffer for new query."""
        with self._lock:
            self._current_query_prompt = prompt
            self._reset_buffer()
            self._query_complete_event = threading.Event()

    def on_query_complete(self, messages: list[Message]) -> None:
        """Signal query completion."""
        with self._lock:
            if self._query_complete_event:
                self._query_complete_event.set()

    def on_stream_start(self) -> None:
        """Mark streaming as active."""
        with self._lock:
            self._streaming = True

    def on_stream_end(self) -> None:
        """Mark streaming as inactive."""
        with self._lock:
            self._streaming = False

    def get_messages(self) -> list[Message]:
        """Get all buffered messages for current query."""
        with self._lock:
            return list(self._current_query_messages)

    def wait_for_completion(self, timeout: float = 60.0) -> bool:
        """Wait for query to complete."""
        with self._lock:
            event = self._query_complete_event
        if event:
            return event.wait(timeout=timeout)
        return False

    def is_complete(self) -> bool:
        """Check if current query is complete."""
        with self._lock:
            if self._query_complete_event:
                return self._query_complete_event.is_set()
            return False


class AsyncMessageEventListener:
    """Base class for async message event handlers.

    Implement this interface to create custom async message handlers.
    All methods here are async and should be awaited.

    Example:
        ```python
        class MyAsyncHandler(AsyncMessageEventListener):
            async def on_message(self, message: Message):
                print(f"Received: {type(message).__name__}")

            async def on_query_start(self, prompt: str):
                print(f"Query started: {prompt}")

            async def on_query_complete(self, messages: list[Message]):
                print(f"Query complete with {len(messages)} messages")
        ```
    """

    async def on_message(self, message: Message) -> None:
        """Called when any message is received (async)."""

    async def on_error(self, error: Exception) -> None:
        """Called when an error occurs (async)."""

    async def on_query_start(self, prompt: str) -> None:
        """Called when a query starts (async)."""

    async def on_query_complete(self, messages: list[Message]) -> None:
        """Called when a query completes (async)."""

    async def on_stream_start(self) -> None:
        """Called when streaming starts."""

    async def on_stream_end(self) -> None:
        """Called when streaming ends."""


class AsyncDefaultMessageHandler(AsyncMessageEventListener, _MessageBufferMixin):
    """Default async handler that buffers messages by query.

    This handler collects messages for each query using asyncio primitives.
    Thread-safe for async/await patterns.
    """

    def __init__(self) -> None:
        """Initialize the async default handler."""
        self._lock = asyncio.Lock()
        self._query_complete_event: asyncio.Event | None = None
        self._init_buffer()

    async def on_message(self, message: Message) -> None:
        """Buffer message for current query."""
        async with self._lock:
            self._current_query_messages.append(message)

    async def on_query_start(self, prompt: str) -> None:
        """Initialize buffer for new query."""
        async with self._lock:
            self._current_query_prompt = prompt
            self._reset_buffer()
            self._query_complete_event = asyncio.Event()

    async def on_query_complete(self, messages: list[Message]) -> None:
        """Signal query completion."""
        async with self._lock:
            if self._query_complete_event:
                self._query_complete_event.set()

    async def on_stream_start(self) -> None:
        """Mark streaming as active."""
        async with self._lock:
            self._streaming = True

    async def on_stream_end(self) -> None:
        """Mark streaming as inactive."""
        async with self._lock:
            self._streaming = False

    async def get_messages(self) -> list[Message]:
        """Get all buffered messages for current query."""
        async with self._lock:
            return list(self._current_query_messages)

    async def wait_for_completion(self, timeout: float = 60.0) -> bool:
        """Wait for query to complete."""
        # Get event outside lock to avoid deadlock
        async with self._lock:
            event = self._query_complete_event
        if event:
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
                return True
            except asyncio.TimeoutError:
                return False
        return False

    async def is_complete(self) -> bool:
        """Check if current query is complete."""
        async with self._lock:
            if self._query_complete_event:
                return self._query_complete_event.is_set()
            return False
