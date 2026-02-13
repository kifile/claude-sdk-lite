"""Session-based client for continuous conversations with Claude Code.

This module provides clients that maintain session context across multiple queries,
using a persistent subprocess with stdin/stdout communication.

Both synchronous and asynchronous implementations are provided with event-driven
message handling via MessageEventListener.
"""

import asyncio
import json
import logging
import os
import threading
import typing
import uuid
from typing import Any, Union

from claude_sdk_lite.async_persistent_executor import AsyncPersistentProcessManager
from claude_sdk_lite.message_handler import (
    AsyncMessageEventListener,
    MessageEventListener,
)
from claude_sdk_lite.message_parser import MessageParseError, parse_message
from claude_sdk_lite.options import ClaudeOptions
from claude_sdk_lite.persistent_executor import PersistentProcessManager
from claude_sdk_lite.types import Message, ResultMessage

logger = logging.getLogger(__name__)

# Type alias for message handlers
SyncMessageHandler = MessageEventListener
AsyncMessageHandler = Union[AsyncMessageEventListener, MessageEventListener]


class _BaseClient:
    """Shared base class for Claude clients.

    Contains common logic for command building, session management, and logging.
    """

    def __init__(self, options: ClaudeOptions | None = None):
        """Initialize base client.

        Args:
            options: Optional configuration. If not provided, defaults will be used.
        """
        self.options = options or ClaudeOptions()
        self._debug = os.environ.get("CLAUDE_SDK_DEBUG", "false").lower() == "true"
        self._setup_session_id()

    def _setup_session_id(self) -> None:
        """Generate or use provided session_id."""
        if not self.options.session_id:
            self.session_id = str(uuid.uuid4())
            # Use model_copy to preserve immutability of options
            self.options = self.options.model_copy(update={"session_id": self.session_id})
        else:
            self.session_id = self.options.session_id

    def _build_command(self) -> list[str]:
        """Build the command list for persistent subprocess.

        Returns:
            List of command arguments.
        """
        cmd = self.options.build_command()
        cmd.extend(
            [
                "--output-format",
                "stream-json",
                "--input-format",
                "stream-json",
                "--verbose",
            ]
        )
        return cmd

    def _log_debug(self, message: str, *args: Any) -> None:
        """Log debug message only if debug mode is enabled."""
        if self._debug:
            logger.debug(message, *args)


class ClaudeClient(_BaseClient):
    """Synchronous client for continuous conversations with Claude Code.

    This client maintains a persistent subprocess connection with a background
    listener thread that continuously reads stdout and invokes handler callbacks.

    Example:
        ```python
        from claude_sdk_lite import ClaudeClient, ClaudeOptions, DefaultMessageHandler

        handler = DefaultMessageHandler()
        with ClaudeClient(options=ClaudeOptions(model="sonnet"), message_handler=handler) as client:
            client.send_request("What is the capital of France?")
            handler.wait_for_completion(timeout=30.0)
            messages = handler.get_messages()
        ```

    Args:
        message_handler: Required message event listener for handling messages.
        options: Configuration options for the Claude Code CLI.

    Attributes:
        session_id: The unique session identifier for this conversation.
        options: The ClaudeOptions used for this session.
        message_handler: The message event handler (read-only).

    Raises:
        ValueError: If message_handler is None.
    """

    def __init__(
        self,
        message_handler: SyncMessageHandler,
        options: ClaudeOptions | None = None,
    ):
        """Initialize the client.

        Args:
            message_handler: Required message event listener.
            options: Optional configuration.

        Raises:
            ValueError: If message_handler is None.
        """
        if message_handler is None:
            raise ValueError("message_handler is required and cannot be None")

        super().__init__(options)
        self._handler = message_handler
        self._manager = PersistentProcessManager()

        # Request state tracking
        self._request_lock = threading.Lock()
        self._request_in_progress = False

        # Background listener thread
        self._listener_thread: threading.Thread | None = None
        self._listener_running = False
        self._listener_stop_event: threading.Event | None = None

    @property
    def is_connected(self) -> bool:
        """Check if the client is currently connected."""
        return self._manager.is_alive()

    @property
    def message_handler(self) -> SyncMessageHandler:
        """Get the message handler (read-only)."""
        return self._handler

    def __enter__(self) -> "ClaudeClient":
        """Enter context manager - auto-starts persistent process and listener."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager - auto-stops persistent process and listener."""
        _ = exc_type, exc_val, exc_tb
        self.disconnect()

    def connect(self) -> None:
        """Start persistent subprocess and background listener."""
        if self._manager.is_alive():
            return

        cmd = self._build_command()
        kwargs = self.options.build_subprocess_kwargs()
        self._manager.start(cmd, **kwargs)
        self._start_listener()

    def disconnect(self) -> None:
        """Stop persistent subprocess, background listener, and cleanup resources."""
        self._stop_listener()
        self._manager.stop()

    def send_request(self, prompt: str) -> None:
        """Send a user query to the Claude CLI.

        Args:
            prompt: The user prompt to send.

        Raises:
            RuntimeError: If the client is not connected.
        """
        if not self._manager.is_alive():
            raise RuntimeError("Client not connected. Call connect() first or use context manager.")

        # Notify handler of query start first (this resets buffer in DefaultMessageHandler)
        self._safe_callback(lambda: self._handler.on_query_start(prompt))

        # Mark request as in progress
        with self._request_lock:
            self._request_in_progress = True

        # Send request
        message = {
            "type": "user",
            "message": {"role": "user", "content": prompt},
            "session_id": self.session_id,
        }

        self._log_debug("Sending message via stdin: %s", message)
        self._manager.write_request(message)

    def interrupt(self) -> None:
        """Send interrupt signal via stdin.

        Only sends interrupt if there is a request currently in progress.

        Raises:
            RuntimeError: If the client is not connected.
        """
        if not self._manager.is_alive():
            raise RuntimeError("Client not connected. Call connect() first or use context manager.")

        # Only interrupt if there's a request in progress
        with self._request_lock:
            if not self._request_in_progress:
                self._log_debug("Ignoring interrupt: no request in progress")
                return
            self._request_in_progress = False

        # Send interrupt signal
        self._manager.write_interrupt()

    @property
    def stderr_output(self) -> list[str]:
        """Get captured stderr output."""
        return self._manager.get_stderr()

    # Listener management

    def _start_listener(self) -> None:
        """Start background listener thread."""
        if self._listener_running:
            return

        self._listener_stop_event = threading.Event()
        self._listener_running = True
        self._listener_thread = threading.Thread(
            target=self._listener_loop,
            name="claude-message-listener",
            daemon=True,
        )
        self._listener_thread.start()
        self._log_debug("Background listener thread started")

    def _stop_listener(self) -> None:
        """Stop background listener thread."""
        if not self._listener_running:
            return

        self._listener_running = False
        if self._listener_stop_event:
            self._listener_stop_event.set()

        if self._listener_thread:
            self._listener_thread.join(timeout=2.0)
            if self._listener_thread.is_alive():
                logger.warning("Listener thread did not stop gracefully")
            self._listener_thread = None

        self._log_debug("Background listener thread stopped")

    # Listener loop

    def _listener_loop(self) -> None:
        """Background listener loop - reads from stdout and invokes callbacks."""
        self._log_debug("Listener loop started")

        try:
            while self._listener_running and not self._listener_stop_event.is_set():
                try:
                    for line in self._manager.read_lines(timeout=0.5):
                        if not self._listener_running:
                            break
                        self._process_line(line)

                except Exception as e:
                    self._log_debug("Listener error: %s", e)
                    logger.debug("Listener loop error: %s", e)
                    self._handle_error(e)
                    if self._listener_stop_event:
                        self._listener_stop_event.wait(1.0)

        except Exception as e:
            logger.error("Fatal error in listener loop: %s", e)
            self._handle_error(e)

        self._log_debug("Listener loop ended")

    def _process_line(self, line: bytes) -> None:
        """Process a single line from stdout."""
        self._log_debug("Received line: %d bytes", len(line))

        line_str = line.decode().strip()
        if not line_str:
            return

        try:
            data = json.loads(line_str)
            self._log_debug("Parsed JSON data: %s", data)

            message = parse_message(data)

            self._handle_message(message)

        except (json.JSONDecodeError, MessageParseError) as e:
            self._log_debug("Parse error: %s", e)
            self._log_debug("Line: %s", line_str[:200])
            logger.debug("Failed to parse message: %s", e)
            self._handle_error(e)

    def _handle_message(self, message: Message) -> None:
        """Handle a message by invoking callbacks."""
        self._safe_callback(lambda: self._handler.on_message(message))

        if isinstance(message, ResultMessage):
            # Reset request state when query completes
            with self._request_lock:
                self._request_in_progress = False

            messages = []
            if hasattr(self._handler, "get_messages"):
                messages = self._handler.get_messages()
            self._safe_callback(lambda: self._handler.on_query_complete(messages))
            self._log_debug("Query complete, %d messages", len(messages))

    def _handle_error(self, error: Exception) -> None:
        """Handle an error by invoking error callback."""
        self._safe_callback(lambda: self._handler.on_error(error))

    def _safe_callback(self, callback: typing.Callable[[], None]) -> None:
        """Invoke a user callback with exception handling."""
        try:
            callback()
        except Exception as e:
            self._log_debug("Handler callback error: %s", e)
            logger.error("Handler callback error: %s", e)


class AsyncClaudeClient(_BaseClient):
    """Asynchronous client for continuous conversations with Claude Code.

    This client maintains a persistent subprocess connection with a background
    listener task that continuously reads stdout and invokes handler callbacks.

    Example:
        ```python
        from claude_sdk_lite import AsyncClaudeClient, ClaudeOptions, AsyncDefaultMessageHandler

        handler = AsyncDefaultMessageHandler()
        async with AsyncClaudeClient(options=ClaudeOptions(model="sonnet"), message_handler=handler) as client:
            await client.send_request("What is the capital of France?")
            await handler.wait_for_completion(timeout=30.0)
            messages = await handler.get_messages()
        ```

    Args:
        message_handler: Required message event listener for handling messages.
        options: Configuration options for the Claude Code CLI.

    Attributes:
        session_id: The unique session identifier for this conversation.
        options: The ClaudeOptions used for this session.
        message_handler: The message event handler (read-only).

    Raises:
        ValueError: If message_handler is None.
    """

    def __init__(
        self,
        message_handler: AsyncMessageHandler,
        options: ClaudeOptions | None = None,
    ):
        """Initialize the async client.

        Args:
            message_handler: Required message event listener.
            options: Optional configuration.

        Raises:
            ValueError: If message_handler is None.
        """
        if message_handler is None:
            raise ValueError("message_handler is required and cannot be None")

        super().__init__(options)
        self._handler = message_handler
        self._manager = AsyncPersistentProcessManager()

        # Cache handler type to avoid repeated isinstance checks
        self._is_async_handler = isinstance(message_handler, AsyncMessageEventListener)

        # Cache get_messages type for performance
        self._has_async_get_messages = (
            self._is_async_handler
            and hasattr(message_handler, "get_messages")
            and asyncio.iscoroutinefunction(message_handler.get_messages)
        )

        # Request state tracking
        self._request_lock = asyncio.Lock()
        self._request_in_progress = False

        # Background listener task
        self._listener_task: asyncio.Task[None] | None = None
        self._listener_running = False

    @property
    def is_connected(self) -> bool:
        """Check if the client is currently connected."""
        return self._manager.is_alive()

    @property
    def message_handler(self) -> AsyncMessageHandler:
        """Get the message handler (read-only)."""
        return self._handler

    async def __aenter__(self) -> "AsyncClaudeClient":
        """Enter async context manager - auto-starts persistent process and listener."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager - auto-stops persistent process and listener."""
        _ = exc_type, exc_val, exc_tb
        await self.disconnect()

    async def connect(self) -> None:
        """Start persistent subprocess and background listener."""
        if self._manager.is_alive():
            return

        cmd = self._build_command()
        kwargs = self.options.build_subprocess_kwargs()
        await self._manager.start(cmd, **kwargs)
        await self._start_listener()

    async def disconnect(self) -> None:
        """Stop persistent subprocess, background listener, and cleanup resources."""
        await self._manager.stop()
        await self._stop_listener()

    async def send_request(self, prompt: str) -> None:
        """Send a user query to the Claude CLI.

        Args:
            prompt: The user prompt to send.

        Raises:
            RuntimeError: If the client is not connected.
        """
        if not self._manager.is_alive():
            raise RuntimeError(
                "Client not connected. Call connect() first or use async context manager."
            )

        # Notify handler of query start first (this resets buffer in DefaultMessageHandler)
        if self._is_async_handler:
            await self._handler.on_query_start(prompt)
        else:
            self._handler.on_query_start(prompt)

        # Mark request as in progress
        async with self._request_lock:
            self._request_in_progress = True

        # Send request
        message = {
            "type": "user",
            "message": {"role": "user", "content": prompt},
            "session_id": self.session_id,
        }

        self._log_debug("Sending message via stdin: %s", message)
        await self._manager.write_request(message)

    async def interrupt(self) -> None:
        """Send interrupt signal via stdin.

        Only sends interrupt if there is a request currently in progress.

        Raises:
            RuntimeError: If the client is not connected.
        """
        if not self._manager.is_alive():
            raise RuntimeError(
                "Client not connected. Call connect() first or use async context manager."
            )

        # Only interrupt if there's a request in progress
        async with self._request_lock:
            if not self._request_in_progress:
                self._log_debug("Ignoring interrupt: no request in progress")
                return
            self._request_in_progress = False

        # Send interrupt signal
        await self._manager.write_interrupt()

    async def get_stderr(self) -> list[str]:
        """Get captured stderr output."""
        return await self._manager.get_stderr()

    # Listener management

    async def _start_listener(self) -> None:
        """Start background listener task."""
        if self._listener_task and not self._listener_task.done():
            return

        self._listener_running = True
        self._listener_task = asyncio.create_task(
            self._listener_loop(),
            name="async-claude-message-listener",
        )
        self._log_debug("Background listener task started")

    async def _stop_listener(self) -> None:
        """Stop background listener task."""
        if not self._listener_running:
            return

        self._listener_running = False

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await asyncio.wait_for(self._listener_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._listener_task = None

        self._log_debug("Background listener task stopped")

    # Listener loop

    async def _listener_loop(self) -> None:
        """Async background listener loop - reads from stdout and invokes callbacks."""
        self._log_debug("Async listener loop started")

        try:
            while self._listener_running:
                try:
                    async for line in self._manager.read_lines(timeout=0.5):
                        if not self._listener_running:
                            break
                        await self._process_line_async(line)

                except Exception as e:
                    self._log_debug("Listener error: %s", e)
                    logger.debug("Listener loop error: %s", e)
                    await self._handle_error_async(e)
                    await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            self._log_debug("Listener loop cancelled")
            raise
        except Exception as e:
            logger.error("Fatal error in async listener loop: %s", e)
            await self._handle_error_async(e)

        self._log_debug("Async listener loop ended")

    async def _process_line_async(self, line: bytes) -> None:
        """Process a single line from stdout (async version)."""
        self._log_debug("Received line: %d bytes", len(line))

        line_str = line.decode().strip()
        if not line_str:
            return

        try:
            data = json.loads(line_str)
            self._log_debug("Parsed JSON data: %s", data)

            message = parse_message(data)

            await self._handle_message_async(message)

        except (json.JSONDecodeError, MessageParseError) as e:
            self._log_debug("Parse error: %s", e)
            self._log_debug("Line: %s", line_str[:200])
            logger.debug("Failed to parse message: %s", e)
            await self._handle_error_async(e)

    async def _handle_message_async(self, message: Message) -> None:
        """Handle a message (async version)."""
        # Invoke on_message callback
        if self._is_async_handler:
            await self._handler.on_message(message)
        else:
            self._handler.on_message(message)

        # Handle result message
        if isinstance(message, ResultMessage):
            # Reset request state when query completes
            async with self._request_lock:
                self._request_in_progress = False

            messages = []
            if hasattr(self._handler, "get_messages"):
                if self._has_async_get_messages:
                    messages = await self._handler.get_messages()
                else:
                    messages = self._handler.get_messages()

            if self._is_async_handler:
                await self._handler.on_query_complete(messages)
            else:
                self._handler.on_query_complete(messages)

            self._log_debug("Query complete, %d messages", len(messages))

    async def _handle_error_async(self, error: Exception) -> None:
        """Handle an error (async version)."""
        if self._is_async_handler:
            await self._handler.on_error(error)
        else:
            self._handler.on_error(error)
