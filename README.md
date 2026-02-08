# Claude SDK Lite

A lightweight Python SDK for [Claude Code CLI](https://github.com/anthropics/claude-code) using subprocess.

## 🚀 Features

- 🪶 **Lightweight** - Only depends on Pydantic, uses your installed claudecode CLI
- ✅ **Type-safe** - Full Pydantic model validation
- 🔧 **Complete Coverage** - Supports all Claude Code CLI parameters
- 📝 **Easy to Use** - Simple, async API compatible with official claude-agent-sdk
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

## 📖 API Documentation

### `query(prompt, options=None)`

Query Claude Code, returning an async iterator of messages.

**Parameters:**
- `prompt` (str): The prompt to send to Claude
- `options` (ClaudeOptions | None): Optional configuration

**Yields:**
- `Message`: Messages from the conversation (AssistantMessage, SystemMessage, ResultMessage)

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

## 🔧 Comparison with Official SDK

| Feature | claude-sdk-lite | claude-agent-sdk |
|---------|-----------------|------------------|
| Package Size | ~50KB | ~100MB+ |
| Dependencies | Pydantic | anyio, anthropic, ... |
| CLI | User installed | Bundled |
| API | Compatible | - |
| Message Types | Full support | Full support |
| Use Case | Projects with CLI | Standalone deployment |

## 🔄 Migration from Official SDK

```python
# Official SDK
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(model="sonnet")
async for message in query(prompt="Hello", options=options):
    print(message)

# claude-sdk-lite (just change imports)
from claude_sdk_lite import query, ClaudeOptions

options = ClaudeOptions(model="sonnet")
async for message in query(prompt="Hello", options=options):
    print(message)
```

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

This SDK is inspired by [Anthropic's official claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-python) and provides a lightweight alternative with compatible API.
