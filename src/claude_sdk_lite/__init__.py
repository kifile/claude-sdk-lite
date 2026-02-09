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

__version__ = "0.2.0"

from .async_persistent_executor import AsyncPersistentProcessManager
from .client import AsyncClaudeClient, ClaudeClient
from .exceptions import (
    ClaudeSDKLiteError,
    CLIExecutionError,
    CLINotFoundError,
    QueryError,
)
from .message_handler import (
    AsyncDefaultMessageHandler,
    AsyncMessageEventListener,
    DefaultMessageHandler,
    MessageEventListener,
)
from .message_parser import MessageParseError, parse_message
from .options import ClaudeOptions
from .persistent_executor import PersistentProcessManager
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
    UnknownMessage,
    UserMessage,
)

__all__ = [
    # Version
    "__version__",
    # Session clients
    "ClaudeClient",
    "AsyncClaudeClient",
    # Process managers
    "PersistentProcessManager",
    "AsyncPersistentProcessManager",
    # Core functions (sync)
    "query",
    "query_text",
    # Core functions (async)
    "async_query",
    "async_query_text",
    # Options
    "ClaudeOptions",
    # Message handlers
    "MessageEventListener",
    "DefaultMessageHandler",
    "AsyncMessageEventListener",
    "AsyncDefaultMessageHandler",
    # Message types
    "Message",
    "AssistantMessage",
    "UserMessage",
    "SystemMessage",
    "ResultMessage",
    "StreamEvent",
    "UnknownMessage",
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
