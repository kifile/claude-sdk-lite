# Claude SDK Lite

A lightweight Python SDK for [Claude Code CLI](https://github.com/anthropics/claude-code) using subprocess.

## Why This Project

The official [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-python) is a comprehensive solution that bundles the Claude Code CLI (~100MB) and only provides an async API. For many use cases, this is overkill.

**claude-sdk-lite** is designed for developers who:
- Already have Claude Code CLI installed
- Need a simple sync API without asyncio complexity
- Want a lightweight package with minimal dependencies

## Installation

```bash
# Prerequisites
npm install -g @anthropic-ai/claude-code

# Install the SDK
pip install claude-sdk-lite
```

## Quick Start

```python
from claude_sdk_lite import query, AssistantMessage, TextBlock

for message in query(prompt="What is the capital of France?"):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text)
```

## Comparison with Official SDK

| Feature | claude-sdk-lite | claude-agent-sdk |
|---------|-----------------|------------------|
| Package Size | ~50KB | ~100MB+ |
| Dependencies | 1 (Pydantic) | 3+ |
| API | Sync + Async | Async only |
| CLI | User installed | Bundled |
| Custom MCP servers | ❌ | ✅ |
| Hooks system | ❌ | ✅ |

**Choose claude-sdk-lite** if you need a lightweight, simple API for basic queries and multi-turn conversations.

**Choose claude-agent-sdk** if you need custom MCP servers, hooks, or a standalone deployment with bundled CLI.

## Documentation

Full API documentation, examples, and migration guides: → [**DOCS.md**](DOCS.md)

## Changelog

### [0.3.0] - 2026-02-13
- **Enhanced Message Parsing** - Improved robustness with `UnknownMessage` fallback for forward compatibility
- **Better User Message Handling** - Proper display of user input when `replay_user_messages` is enabled
- **Interrupt Signal Support** - Add `InterruptBlock` content type for interrupt signal display
- **Async Interrupt Handling** - Improved `CancelledError` propagation in async client
- **Extended Type Support** - Add `ControlResponseMessage` for control request acknowledgments
- **API Improvements** - Moved `build_subprocess_kwargs()` to `ClaudeOptions` for better encapsulation

### [0.2.1] - 2025-02-10
- **Echo Mode** - New `echo_mode` option to echo user input and interrupt signals through message stream

### [0.2.0] - 2025-02-10
- **Session-Based Clients** - `ClaudeClient` and `AsyncClaudeClient` for multi-turn conversations
- **Event-Driven Architecture** - Real-time message handling via `MessageEventListener`
- **Default Handlers** - Built-in message buffering and synchronization helpers

### [0.1.0] - Initial Release
- Basic query functions with full Claude Code CLI parameter support

## License

MIT License - see LICENSE file for details.

## Acknowledgments

Inspired by [Anthropic's official claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-python).
