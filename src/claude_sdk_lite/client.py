"""Session-based client for continuous conversations with Claude Code.

This module provides a client that maintains session context across multiple queries,
using a persistent subprocess with stdin/stdout communication.
"""

import json
import logging
import os
import uuid
from collections.abc import Iterator
from typing import Any

from claude_sdk_lite.message_parser import MessageParseError, parse_message
from claude_sdk_lite.options import ClaudeOptions
from claude_sdk_lite.persistent_executor import PersistentProcessManager
from claude_sdk_lite.types import Message, ResultMessage

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Synchronous client for continuous conversations with Claude Code.

    This client maintains a persistent subprocess connection, allowing multiple
    queries to be sent over the same session via stdin/stdout communication.

    Example:
        ```python
        from claude_sdk_lite import ClaudeClient, ClaudeOptions

        # Using context manager (recommended)
        with ClaudeClient(options=ClaudeOptions(model="sonnet")) as client:
            # Stream responses
            for msg in client.query_stream("What is the capital of France?"):
                print(msg)

            # Or get complete response
            messages = client.query("What about Germany?")
            for msg in messages:
                print(msg)

        # Manual connect/disconnect
        client = ClaudeClient()
        client.connect()
        try:
            messages = client.query("Hello")
            for msg in messages:
                print(msg)
        finally:
            client.disconnect()
        ```

    Args:
        options: Configuration options for the Claude Code CLI.
                 If None, uses default options. A session_id will be
                 auto-generated if not specified.

    Attributes:
        session_id: The unique session identifier for this conversation.
        options: The ClaudeOptions used for this session.
    """

    def __init__(self, options: ClaudeOptions | None = None):
        """Initialize the client.

        Args:
            options: Optional configuration. If not provided, defaults
                     will be used. A session_id will be generated if
                     not specified in options.
        """
        self.options = options or ClaudeOptions()

        # Generate session_id if not provided
        if not self.options.session_id:
            self.session_id = str(uuid.uuid4())
            self.options = self.options.model_copy(update={"session_id": self.session_id})
        else:
            self.session_id = self.options.session_id

        # Persistent process manager
        self._manager = PersistentProcessManager()

        # Cache debug flag
        self._debug = os.environ.get("CLAUDE_SDK_DEBUG", "false").lower() == "true"

    @property
    def is_connected(self) -> bool:
        """Check if the client is currently connected.

        Returns:
            True if connected, False otherwise.
        """
        return self._manager.is_alive()

    def __enter__(self) -> "ClaudeClient":
        """Enter context manager - auto-starts persistent process.

        Returns:
            The connected client instance.
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager - auto-stops persistent process."""
        _ = exc_type, exc_val, exc_tb  # Unused
        self.disconnect()

    def connect(self) -> None:
        """Start persistent subprocess for session-based interaction.

        Raises:
            CLINotFoundError: If the Claude Code CLI is not found.
            RuntimeError: If already connected.
        """
        if self._manager.is_alive():
            return

        # Build command with stream-json input/output (no --print mode)
        cmd = self._build_command()
        kwargs = self._build_subprocess_kwargs()

        # Start persistent process
        self._manager.start(cmd, **kwargs)

    def disconnect(self) -> None:
        """Stop persistent subprocess and cleanup resources."""
        self._manager.stop()

    def query(self, prompt: str) -> list[Message]:
        """Send a query and return complete list of messages.

        This is a convenience method that collects all messages into a list.
        Use query_stream() for streaming responses.

        Args:
            prompt: The user prompt to send.

        Returns:
            List of Message objects from the conversation.

        Raises:
            RuntimeError: If the client is not connected.

        Example:
            ```python
            with ClaudeClient() as client:
                messages = client.query("What is 2+2?")
                for msg in messages:
                    print(msg)
            ```
        """
        return list(self.query_stream(prompt))

    def query_stream(self, prompt: str) -> Iterator[Message]:
        """Send a query and stream messages from the response.

        This method sends the query via stdin to the persistent process
        and streams responses from stdout.

        Args:
            prompt: The user prompt to send.

        Yields:
            Message objects from the conversation, including AssistantMessage,
            SystemMessage, and finally ResultMessage.

        Raises:
            RuntimeError: If the client is not connected.

        Example:
            ```python
            with ClaudeClient() as client:
                for message in client.query_stream("What is 2+2?"):
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                print(block.text)
            ```
        """
        if not self._manager.is_alive():
            raise RuntimeError("Client not connected. Call connect() first or use context manager.")

        # Prepare user message in JSON format
        message = {
            "type": "user",
            "message": {"role": "user", "content": prompt},
            "session_id": self.session_id,
        }

        if self._debug:
            logger.debug("Sending message via stdin: %s", message)

        # Send message via stdin
        self._manager.write_request(message)

        # Read response from stdout
        message_count = 0
        for line in self._manager.read_lines(timeout=60.0):
            if self._debug:
                logger.debug("Received line: %d bytes", len(line))

            line_str = line.decode().strip()
            if not line_str:
                continue

            try:
                # Parse JSON line
                data = json.loads(line_str)
                if self._debug:
                    logger.debug("Parsed: %s", data.get("type", "unknown"))

                message = parse_message(data)
                message_count += 1
                if self._debug:
                    type_name = type(message).__name__
                    logger.debug("Message #%d: type=%s", message_count, type_name)

                # Yield the message
                yield message

                # If this is a result message, we're done
                if isinstance(message, ResultMessage):
                    if self._debug:
                        logger.debug("Result received, ending stream")
                    break

            except (json.JSONDecodeError, MessageParseError) as e:
                if self._debug:
                    logger.debug("Parse error: %s", e)
                    logger.debug("Line: %s", line_str[:200])
                logger.debug("Failed to parse message: %s", e)
                continue

        if self._debug:
            logger.debug("Query completed: %d messages", message_count)

    def interrupt(self) -> None:
        """Send interrupt signal via stdin.

        This sends an interrupt control request to the Claude CLI,
        which will interrupt the currently running operation.

        Raises:
            RuntimeError: If the client is not connected.
        """
        if not self._manager.is_alive():
            raise RuntimeError("Client not connected. Call connect() first or use context manager.")

        self._manager.write_interrupt()

    @property
    def stderr_output(self) -> list[str]:
        """Get captured stderr output.

        Returns:
            List of stderr lines captured during execution.
        """
        return self._manager.get_stderr()

    def _build_command(self) -> list[str]:
        """Build the command list for persistent subprocess.

        Returns:
            List of command arguments.

        Note:
            This uses --input-format stream-json for stdin communication,
            but does NOT use --print mode (which would exit immediately).
        """
        # Use options to build base command
        cmd = self.options.build_command()

        # Add stream-json input/output format
        # Note: We do NOT use --print mode, which would exit after one query
        # Instead, we use --input-format stream-json to read from stdin
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

    def _build_subprocess_kwargs(self) -> dict[str, Any]:
        """Build subprocess keyword arguments.

        Returns:
            Dictionary of kwargs for subprocess.Popen().
        """
        result: dict[str, Any] = {}

        if self.options.working_dir:
            result["cwd"] = str(self.options.working_dir)

        if self.options.env:
            result["env"] = {**os.environ, **self.options.env}

        return result
