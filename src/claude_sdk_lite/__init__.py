"""Claude SDK Lite - Lightweight subprocess wrapper for Claude Code CLI.

A lightweight alternative to the official claude-agent-sdk that uses
subprocess to call the user's installed claudecode CLI.

Example (sync):
    ```python
    from claude_sdk_lite import query, ClaudeOptions

    options = ClaudeOptions(model="sonnet")

    for message in query(
        prompt="What is the capital of France?",
        options=options
    ):
        print(message)
    ```

Example (async):
    ```python
    from claude_sdk_lite import async_query, ClaudeOptions

    async def main():
        options = ClaudeOptions(model="sonnet")

        async for message in async_query(
            prompt="What is the capital of France?",
            options=options
        ):
            print(message)
    ```
"""

__version__ = "0.1.0"

from .exceptions import (
    ClaudeSDKLiteError,
    CLIExecutionError,
    CLINotFoundError,
    QueryError,
)
from .message_parser import MessageParseError, parse_message
from .options import ClaudeOptions
from .query import (
    async_query,
    async_query_text,
    query,
    query_text,
)
from .types import (
    AssistantMessage,
    ContentBlock,
    Message,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

__all__ = [
    # Version
    "__version__",
    # Core functions (sync)
    "query",
    "query_text",
    # Core functions (async)
    "async_query",
    "async_query_text",
    # Options
    "ClaudeOptions",
    # Message types
    "Message",
    "AssistantMessage",
    "UserMessage",
    "SystemMessage",
    "ResultMessage",
    "StreamEvent",
    # Content blocks
    "ContentBlock",
    "TextBlock",
    "ThinkingBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    # Errors
    "ClaudeSDKLiteError",
    "QueryError",
    "CLINotFoundError",
    "CLIExecutionError",
    "MessageParseError",
    "parse_message",
]
