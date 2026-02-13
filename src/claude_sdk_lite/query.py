"""Query functions for one-shot interactions with Claude Code.

This module provides both synchronous and asynchronous query functions
that use subprocess to call the installed claudecode CLI.

This is a lightweight alternative to the official claude-agent-sdk,
using subprocess to call the user's installed claudecode CLI.
"""

import json
import logging
import os
from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator

from claude_sdk_lite.exceptions import (
    CLIExecutionError,
    CLINotFoundError,
    ProcessExecutionError,
    QueryError,
)
from claude_sdk_lite.executors import AsyncProcessExecutor, SyncProcessExecutor
from claude_sdk_lite.message_parser import MessageParseError, parse_message
from claude_sdk_lite.options import ClaudeOptions
from claude_sdk_lite.types import AssistantMessage, Message, ResultMessage, TextBlock

logger = logging.getLogger(__name__)

# Debug mode flag - check once at module load time for efficiency
_DEBUG = os.environ.get("CLAUDE_SDK_DEBUG", "false").lower() == "true"


def _parse_lines_to_messages(lines: Iterator[bytes]) -> Iterator[Message]:
    """Parse raw lines to Message objects.

    Args:
        lines: Iterator of raw line bytes

    Yields:
        Parsed Message objects
    """
    for line in lines:
        line_str = line.decode().strip()
        if not line_str:
            continue

        try:
            # Parse JSON line
            data = json.loads(line_str)
            if _DEBUG:
                logger.debug("Parsed JSON data: %s", data)
            message = parse_message(data)

            # Yield the message
            yield message

            # If this is a result message, we're done
            if isinstance(message, ResultMessage):
                if message.is_error:
                    logger.error(f"Query completed with error: {message.result}")
                break

        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse JSON line: {line_str[:100]}... - {e}")
            continue
        except MessageParseError as e:
            logger.debug(f"Failed to parse message: {e}")
            continue


async def _async_parse_lines_to_messages(lines: AsyncIterator[bytes]) -> AsyncIterator[Message]:
    """Parse raw lines to Message objects (async version).

    Args:
        lines: Async iterator of raw line bytes

    Yields:
        Parsed Message objects
    """
    async for line in lines:
        line_str = line.decode().strip()
        if not line_str:
            continue

        try:
            # Parse JSON line
            data = json.loads(line_str)
            if _DEBUG:
                logger.debug("Parsed JSON data: %s", data)
            message = parse_message(data)

            # Yield the message
            yield message

            # If this is a result message, we're done
            if isinstance(message, ResultMessage):
                if message.is_error:
                    logger.error(f"Query completed with error: {message.result}")
                break

        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse JSON line: {line_str[:100]}... - {e}")
            continue
        except MessageParseError as e:
            logger.debug(f"Failed to parse message: {e}")
            continue


def query(
    *,
    prompt: str,
    options: ClaudeOptions | None = None,
) -> Generator[Message, None, None]:
    """
    Query Claude Code for one-shot interactions using subprocess (sync version).

    This is a fully synchronous implementation using subprocess.Popen,
    suitable for high-frequency scenarios and use in synchronous contexts.

    When to use query():
    - Simple one-off questions ("What is 2+2?")
    - Batch processing of independent prompts
    - Code generation or analysis tasks
    - Automated scripts and CI/CD pipelines
    - High-frequency API calls (no asyncio overhead)

    Args:
        prompt: The prompt to send to Claude
        options: Optional configuration (defaults to ClaudeOptions() if None)

    Yields:
        Messages from the conversation (AssistantMessage, SystemMessage, ResultMessage)

    Raises:
        CLINotFoundError: If claude CLI is not found
        CLIExecutionError: If CLI execution fails
        MessageParseError: If response parsing fails

    Example - Simple query:
        ```python
        from claude_sdk_lite import query

        for message in query(prompt="What is the capital of France?"):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text)
        ```

    Example - With options:
        ```python
        from claude_sdk_lite import query, ClaudeOptions

        options = ClaudeOptions(
            model="sonnet",
            system_prompt="You are a helpful assistant",
            permission_mode="acceptEdits"
        )

        for message in query(prompt="Create a hello.py file", options=options):
            print(message)
        ```
    """
    if options is None:
        options = ClaudeOptions()

    # Ensure we're using print mode and JSON output
    # Note: verbose is required by CLI when using --print with --output-format=stream-json
    options = options.model_copy(
        update={
            "print_mode": True,
            "output_format": "stream-json",
            "verbose": True,  # Required by CLI for stream-json output
        }
    )

    # Build command
    cmd = options.build_command(prompt)
    kwargs = options.build_subprocess_kwargs()

    # Create executor and execute
    executor = SyncProcessExecutor()

    try:
        # Execute and get raw lines
        lines = executor.execute(cmd, **kwargs)

        # Parse lines to messages
        yield from _parse_lines_to_messages(lines)

    except FileNotFoundError as e:
        # Check if it's the working directory or the CLI
        import os

        cli_path = str(options.cli_path) if options.cli_path else "claude"

        if options.working_dir and not os.path.exists(str(options.working_dir)):
            raise QueryError(f"Working directory does not exist: {options.working_dir}") from e

        raise CLINotFoundError(
            f"Claude Code CLI not found at: {cli_path}\n"
            f"Please install it with:\n"
            f"  npm install -g @anthropic-ai/claude-code\n"
            f"Or specify the path via: ClaudeOptions(cli_path='/path/to/claude')"
        ) from e

    except ProcessExecutionError as e:
        # Handle CLI execution errors from executor
        raise CLIExecutionError(
            e.message,
            exit_code=e.exit_code,
            stderr=e.stderr,
        ) from e


async def async_query(
    *,
    prompt: str,
    options: ClaudeOptions | None = None,
) -> AsyncGenerator[Message, None]:
    """
    Query Claude Code for one-shot interactions using subprocess (async version).

    This is an asynchronous implementation using asyncio.subprocess,
    suitable for async contexts and concurrent operations.

    When to use async_query():
    - Async/await contexts (FastAPI, asyncio apps)
    - Concurrent queries to multiple instances
    - Streaming responses in async applications

    Args:
        prompt: The prompt to send to Claude
        options: Optional configuration (defaults to ClaudeOptions() if None)

    Yields:
        Messages from the conversation (AssistantMessage, SystemMessage, ResultMessage)

    Raises:
        CLINotFoundError: If claude CLI is not found
        CLIExecutionError: If CLI execution fails
        MessageParseError: If response parsing fails

    Example - Simple async query:
        ```python
        from claude_sdk_lite import async_query

        async def main():
            async for message in async_query(prompt="What is the capital of France?"):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(block.text)
        ```

    Example - With options:
        ```python
        from claude_sdk_lite import async_query, ClaudeOptions

        async def main():
            options = ClaudeOptions(
                model="sonnet",
                system_prompt="You are a helpful assistant",
                permission_mode="acceptEdits"
            )

            async for message in async_query(
                prompt="Create a hello.py file",
                options=options
            ):
                print(message)
        ```
    """
    if options is None:
        options = ClaudeOptions()

    # Ensure we're using print mode and JSON output
    # Note: verbose is required by CLI when using --print with --output-format=stream-json
    options = options.model_copy(
        update={
            "print_mode": True,
            "output_format": "stream-json",
            "verbose": True,  # Required by CLI for stream-json output
        }
    )

    # Build command
    cmd = options.build_command(prompt)
    kwargs = options.build_subprocess_kwargs()

    # Create executor and execute
    executor = AsyncProcessExecutor()

    try:
        # Execute and get raw lines
        lines = executor.async_execute(cmd, **kwargs)

        # Parse lines to messages
        async for message in _async_parse_lines_to_messages(lines):
            yield message

    except FileNotFoundError as e:
        # Check if it's the working directory or the CLI
        import os

        cli_path = str(options.cli_path) if options.cli_path else "claude"

        if options.working_dir and not os.path.exists(str(options.working_dir)):
            raise QueryError(f"Working directory does not exist: {options.working_dir}") from e

        raise CLINotFoundError(
            f"Claude Code CLI not found at: {cli_path}\n"
            f"Please install it with:\n"
            f"  npm install -g @anthropic-ai/claude-code\n"
            f"Or specify the path via: ClaudeOptions(cli_path='/path/to/claude')"
        ) from e

    except ProcessExecutionError as e:
        # Handle CLI execution errors from executor
        raise CLIExecutionError(
            e.message,
            exit_code=e.exit_code,
            stderr=e.stderr,
        ) from e


def query_text(
    *,
    prompt: str,
    options: ClaudeOptions | None = None,
) -> str:
    """
    Convenience function to get only the text response from Claude (sync version).

    This simplifies the common case of just wanting Claude's text response
    without dealing with message types and content blocks.

    Args:
        prompt: The prompt to send to Claude
        options: Optional configuration

    Returns:
        The concatenated text response from Claude

    Example:
        ```python
        from claude_sdk_lite import query_text

        response = query_text(
            prompt="What is the capital of France?",
            options=ClaudeOptions(model="haiku")
        )
        print(response)
        # Output: The capital of France is Paris.
        ```
    """
    text_parts = []

    for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)

    return "".join(text_parts)


async def async_query_text(
    *,
    prompt: str,
    options: ClaudeOptions | None = None,
) -> str:
    """
    Convenience function to get only the text response from Claude (async version).

    This simplifies the common case of just wanting Claude's text response
    without dealing with message types and content blocks.

    Args:
        prompt: The prompt to send to Claude
        options: Optional configuration

    Returns:
        The concatenated text response from Claude

    Example:
        ```python
        from claude_sdk_lite import async_query_text

        async def main():
            response = await async_query_text(
                prompt="What is the capital of France?",
                options=ClaudeOptions(model="haiku")
            )
            print(response)
            # Output: The capital of France is Paris.
        ```
    """
    text_parts = []

    async for message in async_query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)

    return "".join(text_parts)
