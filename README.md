# Claude SDK Lite

A lightweight Python SDK for [Claude Code CLI](https://github.com/anthropics/claude-code) using subprocess.

## 🚀 Features

- 🪶 **Lightweight** - Only depends on Pydantic, uses your installed claudecode CLI
- ✅ **Type-safe** - Full Pydantic model validation
- 🔧 **Complete Coverage** - Supports all Claude Code CLI parameters
- 📝 **Easy to Use** - Simple, sync and async API compatible with official claude-agent-sdk
- 🔄 **Message Types** - Full support for AssistantMessage, TextBlock, and more

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
- ✅ **Only need basic query functionality** - Simple one-shot queries, code generation, analysis
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

# Scripts and automation
result = query_text(prompt="Analyze this code", options=ClaudeOptions(model="haiku"))
```

### Choose official claude-agent-sdk if you:

- 🔧 **Need custom MCP servers** - Create in-process tools with direct app state access
- 🔧 **Need hooks system** - Intercept and modify tool calls, implement permission controls
- 🔧 **Need interactive conversations** - Multi-turn dialog, session management, interrupt capabilities
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

# Interactive conversation (official SDK only)
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
| Custom MCP servers | ❌ | ✅ |
| Hooks system | ❌ | ✅ |
| Interactive conversation | ❌ | ✅ |
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

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

This SDK is inspired by [Anthropic's official claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-python) and provides a lightweight alternative with compatible API.
