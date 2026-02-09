# Claude SDK Lite

A lightweight Python SDK for [Claude Code CLI](https://github.com/anthropics/claude-code) using subprocess.

## 📑 Table of Contents

- [Features](#-features)
- [Installation](#-installation)
- [Comparison with Official SDK](#-comparison-with-official-sdk)
- [When to Use](#-when-to-use-claude-sdk-lite-vs-official-sdk)
- [Quick Start](#-quick-start)
- [Migration from Official SDK](#-migration-from-official-sdk)
- [API Documentation](#-api-documentation)
  - [Session-Based Client API](#session-based-client-api)
  - [Message Event Listeners](#message-event-listeners)
  - [Simple Query API](#simple-query-api)
- [Message Types](#-message-types)
- [Examples](#-examples)
- [Release Notes](#-release-notes)

## 🚀 Features

- 🪶 **Lightweight** - Only depends on Pydantic, uses your installed claudecode CLI
- ✅ **Type-safe** - Full Pydantic model validation
- 🔧 **Complete Coverage** - Supports all Claude Code CLI parameters
- 📝 **Easy to Use** - Simple, sync and async API compatible with official claude-agent-sdk
- 🔄 **Message Types** - Full support for AssistantMessage, TextBlock, and more
- 🎯 **Event-Driven** - Real-time message handling via MessageEventListener callbacks
- 🔄 **Session-Based** - Multi-turn conversations with context retention

## 📦 Installation

### Prerequisites

Install Claude Code CLI:

```bash
npm install -g @anthropic-ai/claude-code
```

### Install the SDK

```bash
pip install claude-sdk-lite
```

## 🔧 Comparison with Official SDK

| Feature | claude-sdk-lite | claude-agent-sdk |
|---------|-----------------|------------------|
| Package Size | ~50KB | ~100MB+ |
| Dependencies | Pydantic only | anyio, anthropic, mcp, ... |
| CLI | User installed | Bundled |
| API | Sync + Async | Async only |
| Message Types | Full support | Full support |
| Use Case | Projects with pre-installed CLI | Standalone deployment |

## 💡 When to Use claude-sdk-lite vs Official SDK

### Choose claude-sdk-lite if you:

- ✅ **Need sync API support** - Use in synchronous contexts without asyncio overhead (official SDK is async-only)
- ✅ **Already have Claude Code CLI installed** - Want to avoid downloading bundled CLI (~100MB)
- ✅ **Need multi-turn conversations** - Session-based client with event-driven message handling
- ✅ **Care about package size and dependencies** - Projects with strict dependency requirements
- ✅ **Don't need custom MCP servers** - No need for in-process tools
- ✅ **Don't need hooks system** - No need to intercept tool calls
- ✅ **Lightweight deployment** - CI/CD, containerized environments

**Typical use cases:**
```python
# Simple code generation
for message in query(prompt="Write a Python function to parse JSON"):
    print(message)

# Batch processing
for prompt in prompts:
    response = query_text(prompt=prompt)
    process(response)

# Event-driven multi-turn conversations
from claude_sdk_lite import ClaudeClient, DefaultMessageHandler

handler = DefaultMessageHandler()
with ClaudeClient(message_handler=handler) as client:
    client.send_request("First question")
    handler.wait_for_completion()

    client.send_request("Follow-up question")  # Same session
    handler.wait_for_completion()

# Scripts and automation
result = query_text(prompt="Analyze this code", options=ClaudeOptions(model="haiku"))
```

### Choose official claude-agent-sdk if you:

- 🔧 **Need custom MCP servers** - Create in-process tools with direct app state access
- 🔧 **Need hooks system** - Intercept and modify tool calls, implement permission controls
- 🔧 **Need advanced tool features** - In-process tools with direct app state, tool callbacks
- 🔧 **Deploy without pre-installed CLI** - Need to distribute standalone application
- 🔧 **Need comprehensive error handling** - Built-in retry, connection management, flow control
- 🔧 **Need tool permission callbacks** - Dynamic permission decisions
- 🔧 **Need plugin system** - Extend SDK functionality

**Typical use cases:**
```python
# Custom MCP tools (official SDK only)
@tool("greet", "Greet a user", {"name": str})
async def greet(args):
    return {"content": [{"type": "text", "text": f"Hello, {args['name']}!"}]}

server = create_sdk_mcp_server("my-tools", tools=[greet])

# Hooks system (official SDK only)
async def check_bash_command(input_data, tool_use_id, context):
    if "dangerous" in input_data["tool_input"].get("command", ""):
        return {"permissionDecision": "deny"}
    return {}

options = ClaudeAgentOptions(
    hooks={"PreToolUse": [HookMatcher(matcher="Bash", hooks=[check_bash_command])]}
)

# Advanced tool callbacks (official SDK only)
async with ClaudeSDKClient(options=options) as client:
    await client.query("First question")
    async for msg in client.receive_response():
        print(msg)
    await client.query("Follow-up question")  # Continue same session
```

### Feature Comparison Table

| Feature | claude-sdk-lite | claude-agent-sdk |
|---------|----------------|------------------|
| Basic query | ✅ | ✅ |
| Sync API | ✅ | ❌ |
| Async API | ✅ | ✅ |
| Event-driven messages | ✅ | ✅ |
| Session-based conversation | ✅ | ✅ |
| Custom MCP servers | ❌ | ✅ |
| Hooks system | ❌ | ✅ |
| Tool permission callbacks | ❌ | ✅ |
| Bundled CLI | ❌ | ✅ |
| Package size | ~50KB | ~100MB+ |
| Dependencies | 1 (Pydantic) | 3+ |

## 🎯 Quick Start

### Basic Usage

```python
from claude_sdk_lite import query, AssistantMessage, TextBlock

for message in query(prompt="What is the capital of France?"):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text)
```

### Async Usage

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

### Event-Driven Multi-Turn Conversations

The session-based client with event-driven message handling enables real-time message processing and multi-turn conversations:

```python
from claude_sdk_lite import ClaudeClient, DefaultMessageHandler, ClaudeOptions

# Create handler for message callbacks
handler = DefaultMessageHandler()

# Use context manager for automatic cleanup
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

    # Context is automatically maintained across queries
```

#### Custom Message Handlers

Create custom handlers by implementing `MessageEventListener`:

```python
from claude_sdk_lite import (
    ClaudeClient,
    MessageEventListener,
    AssistantMessage,
    TextBlock,
    ThinkingBlock,
)

class ChatHandler(MessageEventListener):
    def __init__(self):
        self.response_text = []

    def on_query_start(self, prompt: str):
        print(f"\n🤔 Query: {prompt}")

    def on_message(self, message):
        # Process messages in real-time
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text, end="", flush=True)
                    self.response_text.append(block.text)
                elif isinstance(block, ThinkingBlock):
                    print("\n🤯 Thinking...", end="", flush=True)

    def on_query_complete(self, messages):
        print("\n✅ Query complete!")

handler = ChatHandler()

with ClaudeClient(message_handler=handler) as client:
    client.send_request("Explain recursion in simple terms")
    handler.wait_for_completion()
```

#### Async Event-Driven Conversations

```python
import asyncio
from claude_sdk_lite import (
    AsyncClaudeClient,
    AsyncMessageEventListener,
    AsyncDefaultMessageHandler,
)

async def chat_example():
    # Use default async handler
    handler = AsyncDefaultMessageHandler()

    async with AsyncClaudeClient(message_handler=handler) as client:
        await client.send_request("First question")
        await handler.wait_for_completion(timeout=30.0)

        # Continue conversation
        await client.send_request("Follow-up question")
        await handler.wait_for_completion(timeout=30.0)

        messages = await handler.get_messages()
        print(f"Received {len(messages)} messages")

asyncio.run(chat_example())
```

### Simplified Text Response

```python
from claude_sdk_lite import query_text

response = query_text(prompt="What is 2 + 2?")
print(response)  # "2 + 2 equals 4."
```

### With Options

```python
from claude_sdk_lite import query, ClaudeOptions

options = ClaudeOptions(
    model="haiku",
    system_prompt="You are a helpful math tutor",
    max_turns=1,
)

for message in query(
    prompt="Explain calculus in simple terms",
    options=options
):
    print(message)

## 🔄 Migration from Official SDK

```python
# Official SDK (async only)
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    options = ClaudeAgentOptions(model="sonnet")
    async for message in query(prompt="Hello", options=options):
        print(message)

asyncio.run(main())

# claude-sdk-lite - use async_query for async code
import asyncio
from claude_sdk_lite import async_query, ClaudeOptions

async def main():
    options = ClaudeOptions(model="sonnet")
    async for message in async_query(prompt="Hello", options=options):
        print(message)

asyncio.run(main())

# OR use sync API (claude-sdk-lite exclusive!)
from claude_sdk_lite import query, ClaudeOptions

options = ClaudeOptions(model="sonnet")
for message in query(prompt="Hello", options=options):
    print(message)
```

**Key difference:** Official SDK only supports async API, while claude-sdk-lite supports both sync and async APIs.

## 📖 API Documentation

### Session-Based Client API

#### `ClaudeClient(message_handler, options=None)`

Synchronous client for multi-turn conversations with event-driven message handling.

**Parameters:**
- `message_handler` (MessageEventListener): Required handler for message callbacks
- `options` (ClaudeOptions | None): Optional configuration

**Methods:**
- `connect()` - Start the persistent subprocess and listener
- `disconnect()` - Stop the subprocess and cleanup
- `send_request(prompt)` - Send a query to Claude
- `interrupt()` - Interrupt the current query

**Properties:**
- `is_connected` - Check if client is connected
- `message_handler` - Get the message handler (read-only)
- `session_id` - The session identifier
- `stderr_output` - Get captured stderr output

**Example:**
```python
from claude_sdk_lite import ClaudeClient, DefaultMessageHandler

handler = DefaultMessageHandler()
with ClaudeClient(message_handler=handler) as client:
    client.send_request("Hello!")
    handler.wait_for_completion(timeout=30.0)

    # Continue conversation
    client.send_request("Tell me more")
    handler.wait_for_completion(timeout=30.0)
```

#### `AsyncClaudeClient(message_handler, options=None)`

Async version of `ClaudeClient` for async/await patterns.

**Example:**
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

### Message Event Listeners

#### `MessageEventListener`

Base class for handling message events in real-time.

**Callback Methods:**
- `on_message(message)` - Called when any message is received
- `on_query_start(prompt)` - Called when a query starts
- `on_query_complete(messages)` - Called when a query completes
- `on_stream_start()` - Called when streaming starts
- `on_stream_end()` - Called when streaming ends
- `on_error(error)` - Called when an error occurs

**Example:**
```python
from claude_sdk_lite import MessageEventListener

class MyHandler(MessageEventListener):
    def on_message(self, message):
        print(f"Received: {type(message).__name__}")

    def on_query_complete(self, messages):
        print(f"Complete! Got {len(messages)} messages")
```

#### `AsyncMessageEventListener`

Async version of `MessageEventListener` with async callback methods.

#### `DefaultMessageHandler`

Default implementation that buffers messages and provides synchronization helpers.

**Methods:**
- `get_messages()` - Get all buffered messages for current query
- `wait_for_completion(timeout=60.0)` - Wait for query to complete
- `is_complete()` - Check if current query is complete

#### `AsyncDefaultMessageHandler`

Async version of `DefaultMessageHandler` with async methods.

### Simple Query API

### `query(prompt, options=None)`

Query Claude Code (sync version), returning a generator of messages.

**Parameters:**
- `prompt` (str): The prompt to send to Claude
- `options` (ClaudeOptions | None): Optional configuration

**Yields:**
- `Message`: Messages from the conversation (AssistantMessage, SystemMessage, ResultMessage)

**Example:**
```python
for message in query(prompt="Hello"):
    print(message)
```

### `async_query(prompt, options=None)`

Query Claude Code (async version), returning an async iterator of messages.

**Parameters:**
- `prompt` (str): The prompt to send to Claude
- `options` (ClaudeOptions | None): Optional configuration

**Yields:**
- `Message`: Messages from the conversation (AssistantMessage, SystemMessage, ResultMessage)

**Example:**
```python
async for message in async_query(prompt="Hello"):
    print(message)
```

### `query_text(prompt, options=None) -> str`

Convenience function that returns only the text response.

**Parameters:**
- `prompt` (str): The prompt to send to Claude
- `options` (ClaudeOptions | None): Optional configuration

**Returns:**
- `str`: The concatenated text response

### `ClaudeOptions`

Configuration options class using Pydantic for validation.

#### Core Options

```python
ClaudeOptions(
    model="sonnet",  # Model: sonnet, opus, haiku
    agent="custom-agent",  # Agent to use
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
    resume="session-id",  # Resume specific session
    session_id="uuid",  # Use specific session ID
)
```

#### Permission Mode

```python
ClaudeOptions(
    permission_mode="acceptEdits",  # Auto-accept file edits
    # Other options: default, plan, bypassPermissions, delegate, dontAsk
)
```

#### Budget Limits

```python
ClaudeOptions(
    max_budget_usd=0.50,  # Maximum spend in USD
    max_turns=10,  # Maximum conversation turns
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

## 📝 Message Types

### `AssistantMessage`

Claude's response message with content blocks.

```python
class AssistantMessage(BaseModel):
    content: list[ContentBlock]  # List of content blocks
    model: str  # Model used
    parent_tool_use_id: str | None
    error: str | None
```

### `TextBlock`

Text content block.

```python
class TextBlock(BaseModel):
    text: str
    type: str = "text"
```

### `ToolUseBlock`

Tool usage block.

```python
class ToolUseBlock(BaseModel):
    id: str
    name: str  # Tool name
    input: dict[str, Any]  # Tool input
    type: str = "tool_use"
```

### `ResultMessage`

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

## 🔗 Examples

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

## 📄 Release Notes

### [0.2.0] - 2025-02-10

**🎉 Major Update: Event-Driven Architecture & Multi-Turn Conversations**

#### New Features
- **Session-Based Clients** - Maintain conversation context across multiple queries
  - `ClaudeClient` - Synchronous client with persistent subprocess
  - `AsyncClaudeClient` - Async version for async/await patterns
  - Automatic session management and context retention

- **Event-Driven Message Handling** - Real-time message processing via callbacks
  - `MessageEventListener` - Base class for custom message handlers
  - `AsyncMessageEventListener` - Async version with async callbacks
  - `DefaultMessageHandler` - Built-in handler with message buffering
  - `AsyncDefaultMessageHandler` - Async default handler

#### Key Benefits
- ✅ **Multi-turn conversations** - Send multiple queries in the same session
- ✅ **Real-time streaming** - Process messages as they arrive via callbacks
- ✅ **Flexible handlers** - Create custom handlers for your use case
- ✅ **Thread-safe** - Safe for concurrent operations
- ✅ **Better control** - Interrupt queries, track completion, access buffered messages

See [examples/](examples/) for complete working examples.

### [0.1.0] - Initial Release

Basic query functions with full Claude Code CLI parameter support.

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

This SDK is inspired by [Anthropic's official claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-python) and provides a lightweight alternative with compatible API.
