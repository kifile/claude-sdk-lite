# Claude SDK Lite - Full Documentation

Complete API reference, usage examples, and migration guide.

## Table of Contents

- [Quick Start](#quick-start)
- [Session-Based Client API](#session-based-client-api)
- [Message Event Listeners](#message-event-listeners)
- [Simple Query API](#simple-query-api)
- [Configuration Options](#configuration-options)
- [Message Types](#message-types)
- [Examples](#examples)
- [Migration from Official SDK](#migration-from-official-sdk)

## Quick Start

### Basic Usage (Sync)

```python
from claude_sdk_lite import query, AssistantMessage, TextBlock

for message in query(prompt="What is the capital of France?"):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text)
```

### Basic Usage (Async)

```python
import asyncio
from claude_sdk_lite import async_query, AssistantMessage, TextBlock

async def main():
    async for message in async_query(prompt="What is the capital of France?"):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)

asyncio.run(main())
```

### Simplified Text Response

```python
from claude_sdk_lite import query_text

response = query_text(prompt="What is 2 + 2?")
print(response)  # "2 + 2 equals 4."
```

## Session-Based Client API

### ClaudeClient

Synchronous client for multi-turn conversations with event-driven message handling.

```python
from claude_sdk_lite import ClaudeClient, DefaultMessageHandler, ClaudeOptions

handler = DefaultMessageHandler()

with ClaudeClient(
    message_handler=handler,
    options=ClaudeOptions(model="sonnet")
) as client:
    # Send first request
    client.send_request("What is the capital of France?")
    handler.wait_for_completion(timeout=30.0)

    # Access all messages from the conversation
    for message in handler.get_messages():
        print(message)

    # Send follow-up in the same session
    client.send_request("What about Germany?")
    handler.wait_for_completion(timeout=30.0)
```

#### Methods

- `connect()` - Start the persistent subprocess and listener
- `disconnect()` - Stop the subprocess and cleanup
- `send_request(prompt)` - Send a query to Claude
- `interrupt()` - Interrupt the current query

#### Properties

- `is_connected` - Check if client is connected
- `message_handler` - Get the message handler (read-only)
- `session_id` - The session identifier
- `stderr_output` - Get captured stderr output

### AsyncClaudeClient

Async version of `ClaudeClient` for async/await patterns.

```python
import asyncio
from claude_sdk_lite import AsyncClaudeClient, AsyncDefaultMessageHandler

async def main():
    handler = AsyncDefaultMessageHandler()
    async with AsyncClaudeClient(message_handler=handler) as client:
        await client.send_request("Hello!")
        await handler.wait_for_completion(timeout=30.0)

asyncio.run(main())
```

## Message Event Listeners

### MessageEventListener

Base class for handling message events in real-time.

```python
from claude_sdk_lite import (
    ClaudeClient,
    MessageEventListener,
    AssistantMessage,
    TextBlock,
)

class ChatHandler(MessageEventListener):
    def on_query_start(self, prompt: str):
        print(f"\n🤔 Query: {prompt}")

    def on_message(self, message):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text, end="", flush=True)

    def on_query_complete(self, messages):
        print(f"\n✅ Complete! Got {len(messages)} messages")

handler = ChatHandler()

with ClaudeClient(message_handler=handler) as client:
    client.send_request("Explain recursion in simple terms")
    handler.wait_for_completion()
```

#### Callback Methods

- `on_message(message)` - Called when any message is received
- `on_query_start(prompt)` - Called when a query starts
- `on_query_complete(messages)` - Called when a query completes
- `on_stream_start()` - Called when streaming starts
- `on_stream_end()` - Called when streaming ends
- `on_error(error)` - Called when an error occurs

### AsyncMessageEventListener

Async version of `MessageEventListener` with async callback methods.

### DefaultMessageHandler

Default implementation that buffers messages and provides synchronization helpers.

#### Methods

- `get_messages()` - Get all buffered messages for current query
- `wait_for_completion(timeout=60.0)` - Wait for query to complete
- `is_complete()` - Check if current query is complete

### AsyncDefaultMessageHandler

Async version of `DefaultMessageHandler` with async methods.

## Simple Query API

### query(prompt, options=None)

Query Claude Code (sync version), returning a generator of messages.

```python
for message in query(prompt="Hello"):
    print(message)
```

### async_query(prompt, options=None)

Query Claude Code (async version), returning an async iterator of messages.

```python
async for message in async_query(prompt="Hello"):
    print(message)
```

### query_text(prompt, options=None) -> str

Convenience function that returns only the text response.

```python
response = query_text(prompt="What is 2 + 2?")
print(response)  # "2 + 2 equals 4."
```

## Configuration Options

### ClaudeOptions

Configuration options class using Pydantic for validation.

```python
from claude_sdk_lite import ClaudeOptions

options = ClaudeOptions(
    model="haiku",
    system_prompt="You are a helpful math tutor",
    max_turns=1,
)

for message in query(prompt="Explain calculus", options=options):
    print(message)
```

#### Core Options

```python
ClaudeOptions(
    model="sonnet",           # Model: sonnet, opus, haiku
    agent="custom-agent",     # Agent to use
)
```

#### System Prompt

```python
ClaudeOptions(
    system_prompt="You are a helpful assistant",
    append_system_prompt="Always be concise",
)
```

#### Tools

```python
ClaudeOptions(
    allowed_tools=["Bash(git:*)", "Read", "Edit"],
    disallowed_tools=["WebFetch"],
    tools=["Bash", "Read", "Write"],
)
```

#### Session Management

```python
ClaudeOptions(
    continue_conversation=True,  # Continue recent conversation
    resume="session-id",         # Resume specific session
    session_id="uuid",           # Use specific session ID
)
```

#### Permission Mode

```python
ClaudeOptions(
    permission_mode="acceptEdits",  # Auto-accept file edits
    # Options: default, plan, bypassPermissions, delegate, dontAsk
)
```

#### Budget Limits

```python
ClaudeOptions(
    max_budget_usd=0.50,  # Maximum spend in USD
    max_turns=10,         # Maximum conversation turns
)
```

#### Custom Agents

```python
ClaudeOptions(
    agents={
        "reviewer": {
            "description": "Code reviewer",
            "prompt": "You are an expert code reviewer",
            "model": "sonnet"
        }
    },
    agent="reviewer"
)
```

#### MCP Servers

```python
ClaudeOptions(
    mcp_config={
        "mcpServers": {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
            }
        }
    }
)
```

#### Echo Mode

```python
ClaudeOptions(
    echo_mode=True,  # Echo user input through message stream
)
```

## Message Types

### AssistantMessage

Claude's response message with content blocks.

```python
class AssistantMessage(BaseModel):
    content: list[ContentBlock]  # List of content blocks
    model: str                   # Model used
    parent_tool_use_id: str | None
    error: str | None
```

### TextBlock

Text content block.

```python
class TextBlock(BaseModel):
    text: str
    type: str = "text"
```

### ToolUseBlock

Tool usage block.

```python
class ToolUseBlock(BaseModel):
    id: str
    name: str                  # Tool name
    input: dict[str, Any]      # Tool input
    type: str = "tool_use"
```

### ResultMessage

Result message with cost and usage information.

```python
class ResultMessage(BaseModel):
    subtype: str
    duration_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    total_cost_usd: float | None
    usage: dict[str, Any] | None
    result: str | None
```

### UserMessage

User message with content blocks (only used with `echo_mode=True`).

```python
class UserMessage(BaseModel):
    content: list[ContentBlock]
```

### InterruptBlock

Interrupt signal content block (used with `echo_mode=True`).

```python
class InterruptBlock(BaseModel):
    type: str = "interrupt"
```

## Examples

Check out the [examples directory](examples/) for complete working examples:

- **[simple_chat.py](examples/simple_chat.py)** - Interactive chat with custom MessageEventListener
- **[simple_async_chat.py](examples/simple_async_chat.py)** - Async version with AsyncMessageEventListener
- **[basic_usage.py](examples/basic_usage.py)** - Simple query examples
- **[basic_async_usage.py](examples/basic_async_usage.py)** - Async query examples

Run examples:
```bash
# Sync chat
python examples/simple_chat.py

# Async chat
python examples/simple_async_chat.py

# With debug mode
CLAUDE_SDK_DEBUG=true python examples/simple_chat.py
```

## Migration from Official SDK

### Async Code

```python
# Official SDK (async only)
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    options = ClaudeAgentOptions(model="sonnet")
    async for message in query(prompt="Hello", options=options):
        print(message)

asyncio.run(main())
```

```python
# claude-sdk-lite
import asyncio
from claude_sdk_lite import async_query, ClaudeOptions

async def main():
    options = ClaudeOptions(model="sonnet")
    async for message in async_query(prompt="Hello", options=options):
        print(message)

asyncio.run(main())
```

### Sync Code (claude-sdk-lite exclusive!)

```python
# claude-sdk-lite sync API (not available in official SDK)
from claude_sdk_lite import query, ClaudeOptions

options = ClaudeOptions(model="sonnet")
for message in query(prompt="Hello", options=options):
    print(message)
```

**Key difference:** Official SDK only supports async API, while claude-sdk-lite supports both sync and async APIs.
