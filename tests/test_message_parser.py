"""Tests for message parsing from CLI output.

Tests that various CLI response formats are correctly parsed.
"""

import pytest

from claude_sdk_lite import MessageParseError, parse_message
from claude_sdk_lite.types import (
    AssistantMessage,
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


class TestParseAssistantMessage:
    """Test parsing assistant messages."""

    def test_simple_text_assistant_message(self):
        """Test parsing assistant message with simple text."""
        data = {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": "Hello, how can I help you?"}],
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, AssistantMessage)
        assert msg.model == "claude-sonnet-4-5"
        assert len(msg.content) == 1
        assert isinstance(msg.content[0], TextBlock)
        assert msg.content[0].text == "Hello, how can I help you?"

    def test_assistant_message_with_thinking(self):
        """Test parsing assistant message with thinking block."""
        data = {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "Let me analyze this step by step...",
                        "signature": "abc123def456",
                    },
                    {"type": "text", "text": "Based on my analysis..."},
                ],
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, AssistantMessage)
        assert len(msg.content) == 2
        assert isinstance(msg.content[0], ThinkingBlock)
        assert msg.content[0].thinking == "Let me analyze this step by step..."
        assert msg.content[0].signature == "abc123def456"
        assert isinstance(msg.content[1], TextBlock)

    def test_assistant_message_with_tool_use(self):
        """Test parsing assistant message with tool use."""
        data = {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5",
                "content": [
                    {"type": "text", "text": "I'll help you with that."},
                    {
                        "type": "tool_use",
                        "id": "toolu_01234abcde",
                        "name": "bash",
                        "input": {"command": "ls -la"},
                    },
                ],
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, AssistantMessage)
        assert len(msg.content) == 2
        assert isinstance(msg.content[1], ToolUseBlock)
        assert msg.content[1].id == "toolu_01234abcde"
        assert msg.content[1].name == "bash"
        assert msg.content[1].input == {"command": "ls -la"}

    def test_assistant_message_with_multiple_tools(self):
        """Test parsing assistant message with multiple tool uses."""
        data = {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_1",
                        "name": "Read",
                        "input": {"file_path": "test.py"},
                    },
                    {
                        "type": "tool_use",
                        "id": "tool_2",
                        "name": "Edit",
                        "input": {"file_path": "test.py", "old_string": "old", "new_string": "new"},
                    },
                ],
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, AssistantMessage)
        assert len(msg.content) == 2
        assert msg.content[0].name == "Read"
        assert msg.content[1].name == "Edit"

    def test_assistant_message_with_error(self):
        """Test parsing assistant message with error field."""
        data = {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": "I encountered an issue."}],
            },
            "error": "Tool execution failed",
        }

        msg = parse_message(data)
        assert isinstance(msg, AssistantMessage)
        assert msg.error == "Tool execution failed"

    def test_assistant_message_with_parent_tool_use_id(self):
        """Test parsing assistant message with parent_tool_use_id."""
        data = {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": "Result from tool"}],
            },
            "parent_tool_use_id": "toolu_parent123",
        }

        msg = parse_message(data)
        assert isinstance(msg, AssistantMessage)
        assert msg.parent_tool_use_id == "toolu_parent123"


class TestParseUserMessage:
    """Test parsing user messages."""

    def test_user_message_with_string_content(self):
        """Test parsing user message with simple string content."""
        data = {"type": "user", "message": {"content": "What is the capital of France?"}}

        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert msg.content == "What is the capital of France?"

    def test_user_message_with_blocks(self):
        """Test parsing user message with content blocks."""
        data = {
            "type": "user",
            "message": {
                "content": [
                    {"type": "text", "text": "Please run this command."},
                    {
                        "type": "tool_use",
                        "id": "user_tool_1",
                        "name": "bash",
                        "input": {"command": "npm test"},
                    },
                ]
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert isinstance(msg.content, list)
        assert len(msg.content) == 2
        assert isinstance(msg.content[0], TextBlock)
        assert isinstance(msg.content[1], ToolUseBlock)

    def test_user_message_with_tool_result(self):
        """Test parsing user message with tool result."""
        data = {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01234",
                        "content": "Command output: success",
                        "is_error": False,
                    }
                ]
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert isinstance(msg.content, list)
        assert len(msg.content) == 1
        assert isinstance(msg.content[0], ToolResultBlock)
        assert msg.content[0].tool_use_id == "toolu_01234"
        assert msg.content[0].content == "Command output: success"
        assert msg.content[0].is_error is False

    def test_user_message_with_tool_result_error(self):
        """Test parsing user message with error tool result."""
        data = {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01234",
                        "content": "Command failed",
                        "is_error": True,
                    }
                ]
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert msg.content[0].is_error is True

    def test_user_message_with_uuid(self):
        """Test parsing user message with UUID."""
        data = {"type": "user", "message": {"content": "Test message"}, "uuid": "user-uuid-12345"}

        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert msg.uuid == "user-uuid-12345"

    def test_user_message_with_parent_tool_use_id(self):
        """Test parsing user message with parent_tool_use_id."""
        data = {
            "type": "user",
            "message": {"content": "Tool result"},
            "parent_tool_use_id": "toolu_parent",
        }

        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert msg.parent_tool_use_id == "toolu_parent"

    def test_user_message_with_tool_use_result(self):
        """Test parsing user message with tool_use_result."""
        data = {
            "type": "user",
            "message": {"content": "Tool feedback"},
            "tool_use_result": {"status": "completed", "output": "Done"},
        }

        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert msg.tool_use_result == {"status": "completed", "output": "Done"}


class TestParseSystemMessage:
    """Test parsing system messages."""

    def test_system_message_config(self):
        """Test parsing system config message."""
        data = {
            "type": "system",
            "subtype": "config",
            "data": {"setting": "value", "enabled": True},
        }

        msg = parse_message(data)
        assert isinstance(msg, SystemMessage)
        assert msg.subtype == "config"
        # SystemMessage.data stores the entire original dict
        assert msg.data == data
        assert msg.data["data"]["setting"] == "value"

    def test_system_message_status(self):
        """Test parsing system status message."""
        data = {
            "type": "system",
            "subtype": "status",
            "data": {"status": "ready", "session_id": "session-123"},
        }

        msg = parse_message(data)
        assert isinstance(msg, SystemMessage)
        assert msg.subtype == "status"


class TestParseResultMessage:
    """Test parsing result messages."""

    def test_result_message_success(self):
        """Test parsing successful result message."""
        data = {
            "type": "result",
            "subtype": "complete",
            "duration_ms": 1500,
            "duration_api_ms": 1200,
            "is_error": False,
            "num_turns": 3,
            "session_id": "sess-abc-123",
            "total_cost_usd": 0.00123,
        }

        msg = parse_message(data)
        assert isinstance(msg, ResultMessage)
        assert msg.subtype == "complete"
        assert msg.duration_ms == 1500
        assert msg.duration_api_ms == 1200
        assert msg.is_error is False
        assert msg.num_turns == 3
        assert msg.session_id == "sess-abc-123"
        assert msg.total_cost_usd == 0.00123

    def test_result_message_error(self):
        """Test parsing error result message."""
        data = {
            "type": "result",
            "subtype": "error",
            "duration_ms": 500,
            "duration_api_ms": 200,
            "is_error": True,
            "num_turns": 0,
            "session_id": "sess-error-123",
            "result": "API request failed: timeout",
        }

        msg = parse_message(data)
        assert isinstance(msg, ResultMessage)
        assert msg.is_error is True
        assert msg.result == "API request failed: timeout"

    def test_result_message_with_usage(self):
        """Test parsing result message with usage information."""
        data = {
            "type": "result",
            "subtype": "complete",
            "duration_ms": 1000,
            "duration_api_ms": 800,
            "is_error": False,
            "num_turns": 1,
            "session_id": "sess-123",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_tokens": 0,
                "cache_read_tokens": 0,
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, ResultMessage)
        assert msg.usage is not None
        assert msg.usage["input_tokens"] == 100
        assert msg.usage["output_tokens"] == 50

    def test_result_message_with_structured_output(self):
        """Test parsing result message with structured output."""
        data = {
            "type": "result",
            "subtype": "complete",
            "duration_ms": 2000,
            "duration_api_ms": 1800,
            "is_error": False,
            "num_turns": 1,
            "session_id": "sess-123",
            "structured_output": {
                "name": "Claude",
                "version": "4.5",
                "capabilities": ["code", "analysis"],
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, ResultMessage)
        assert msg.structured_output == {
            "name": "Claude",
            "version": "4.5",
            "capabilities": ["code", "analysis"],
        }

    def test_result_message_without_optional_fields(self):
        """Test parsing result message without optional fields."""
        data = {
            "type": "result",
            "subtype": "complete",
            "duration_ms": 1000,
            "duration_api_ms": 900,
            "is_error": False,
            "num_turns": 1,
            "session_id": "sess-123",
        }

        msg = parse_message(data)
        assert isinstance(msg, ResultMessage)
        assert msg.total_cost_usd is None
        assert msg.usage is None
        assert msg.result is None
        assert msg.structured_output is None


class TestParseStreamEvent:
    """Test parsing stream events."""

    def test_stream_event_content_delta(self):
        """Test parsing content delta stream event."""
        data = {
            "type": "stream_event",
            "uuid": "msg-uuid-123",
            "session_id": "sess-123",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "Hello"},
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, StreamEvent)
        assert msg.uuid == "msg-uuid-123"
        assert msg.session_id == "sess-123"
        assert msg.event["type"] == "content_block_delta"
        assert msg.event["delta"]["text"] == "Hello"

    def test_stream_event_with_parent_tool_use_id(self):
        """Test parsing stream event with parent_tool_use_id."""
        data = {
            "type": "stream_event",
            "uuid": "msg-uuid-123",
            "session_id": "sess-123",
            "parent_tool_use_id": "toolu_parent",
            "event": {"type": "tool_call_delta"},
        }

        msg = parse_message(data)
        assert isinstance(msg, StreamEvent)
        assert msg.parent_tool_use_id == "toolu_parent"


class TestParseFromJSONString:
    """Test parsing from JSON strings."""

    def test_parse_from_json_string(self):
        """Test parsing message from JSON string."""
        json_str = '{"type": "assistant", "message": {"model": "sonnet", "content": [{"type": "text", "text": "Hi"}]}}'

        msg = parse_message(json_str)
        assert isinstance(msg, AssistantMessage)
        assert msg.model == "sonnet"
        assert msg.content[0].text == "Hi"

    def test_parse_from_invalid_json_string(self):
        """Test parsing invalid JSON string raises error."""
        with pytest.raises(MessageParseError, match="Invalid JSON string"):
            parse_message("not a json")


class TestParseErrors:
    """Test parsing error handling."""

    def test_parse_missing_type(self):
        """Test parsing message without type field raises error."""
        data = {"message": {"model": "sonnet", "content": []}}

        with pytest.raises(MessageParseError, match="missing 'type' field"):
            parse_message(data)

    def test_parse_unknown_type(self):
        """Test parsing message with unknown type returns UnknownMessage."""
        data = {"type": "unknown_type", "data": {}}

        msg = parse_message(data)
        assert isinstance(msg, UnknownMessage)
        assert msg.type == "unknown_type"
        assert msg.raw_data == data

    def test_parse_non_dict_data(self):
        """Test parsing non-dict data raises error."""
        with pytest.raises(MessageParseError, match="Invalid message data type"):
            parse_message(["list", "not", "dict"])

    def test_parse_assistant_message_missing_required_field(self):
        """Test parsing assistant message with missing required field."""
        data = {
            "type": "assistant",
            "message": {
                # Missing "model" field
                "content": []
            },
        }

        with pytest.raises(MessageParseError, match="Missing required field"):
            parse_message(data)

    def test_parse_result_message_missing_required_field(self):
        """Test parsing result message with missing required field."""
        data = {
            "type": "result",
            "subtype": "complete",
            # Missing "duration_ms" and other required fields
        }

        with pytest.raises(MessageParseError, match="Missing required field"):
            parse_message(data)


class TestRealWorldScenarios:
    """Test parsing of realistic CLI output scenarios."""

    def test_complete_conversation_flow(self):
        """Test parsing a complete conversation flow."""
        messages = [
            # User message
            {"type": "user", "message": {"content": "What files are in the current directory?"}},
            # Assistant thinking
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-5",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "I need to list the files",
                            "signature": "sig1",
                        }
                    ],
                },
            },
            # Assistant tool use
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-5",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool_1",
                            "name": "bash",
                            "input": {"command": "ls"},
                        }
                    ],
                },
            },
            # Tool result
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool_1",
                            "content": "file1.py\nfile2.py\n",
                            "is_error": False,
                        }
                    ]
                },
            },
            # Final response
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-5",
                    "content": [
                        {"type": "text", "text": "I found two files: file1.py and file2.py"}
                    ],
                },
            },
            # Result
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 3500,
                "duration_api_ms": 3000,
                "is_error": False,
                "num_turns": 2,
                "session_id": "sess-complete",
                "total_cost_usd": 0.002,
            },
        ]

        parsed = [parse_message(msg) for msg in messages]

        assert isinstance(parsed[0], UserMessage)
        assert isinstance(parsed[1], AssistantMessage)
        assert isinstance(parsed[1].content[0], ThinkingBlock)
        assert isinstance(parsed[2], AssistantMessage)
        assert isinstance(parsed[2].content[0], ToolUseBlock)
        assert isinstance(parsed[3], UserMessage)
        assert isinstance(parsed[3].content[0], ToolResultBlock)
        assert isinstance(parsed[4], AssistantMessage)
        assert isinstance(parsed[5], ResultMessage)

    def test_error_scenario(self):
        """Test parsing an error scenario."""
        messages = [
            {"type": "user", "message": {"content": "Delete all files"}},
            {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-5",
                    "content": [
                        {"type": "text", "text": "I cannot delete files without confirmation."}
                    ],
                },
            },
            {
                "type": "result",
                "subtype": "error",
                "duration_ms": 100,
                "duration_api_ms": 50,
                "is_error": True,
                "num_turns": 0,
                "session_id": "sess-error",
                "result": "User request denied",
            },
        ]

        parsed = [parse_message(msg) for msg in messages]

        assert isinstance(parsed[2], ResultMessage)
        assert parsed[2].is_error is True
        assert parsed[2].result == "User request denied"

    def test_multi_tool_conversation(self):
        """Test conversation with multiple tool interactions."""
        data = {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5",
                "content": [
                    {"type": "text", "text": "I'll help you analyze the code."},
                    {
                        "type": "tool_use",
                        "id": "tool_1",
                        "name": "Read",
                        "input": {"file_path": "src/main.py"},
                    },
                    {
                        "type": "tool_use",
                        "id": "tool_2",
                        "name": "Read",
                        "input": {"file_path": "tests/test_main.py"},
                    },
                    {
                        "type": "tool_use",
                        "id": "tool_3",
                        "name": "bash",
                        "input": {"command": "pytest tests/"},
                    },
                ],
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, AssistantMessage)
        assert len(msg.content) == 4
        assert msg.content[1].name == "Read"
        assert msg.content[2].name == "Read"
        assert msg.content[3].name == "bash"


class TestParseAssistantMessageWithToolResult:
    """Test parsing assistant messages with tool_result blocks."""

    def test_assistant_message_with_tool_result(self):
        """Test parsing assistant message with tool_result block (edge case)."""
        # While uncommon, assistant messages can contain tool_result blocks
        data = {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5",
                "content": [
                    {"type": "text", "text": "Here is the tool result."},
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01234",
                        "content": "Command output: success",
                        "is_error": False,
                    },
                ],
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, AssistantMessage)
        assert len(msg.content) == 2
        assert isinstance(msg.content[0], TextBlock)
        assert isinstance(msg.content[1], ToolResultBlock)
        assert msg.content[1].tool_use_id == "toolu_01234"
        assert msg.content[1].content == "Command output: success"
        assert msg.content[1].is_error is False

    def test_assistant_message_with_mixed_blocks(self):
        """Test assistant message with all types of blocks."""
        data = {
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-5",
                "content": [
                    {
                        "type": "thinking",
                        "thinking": "I need to check something",
                        "signature": "sig1",
                    },
                    {"type": "text", "text": "Let me use a tool."},
                    {
                        "type": "tool_use",
                        "id": "tool_1",
                        "name": "Read",
                        "input": {"file_path": "test.py"},
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool_1",
                        "content": "file content",
                        "is_error": False,
                    },
                    {"type": "text", "text": "Done!"},
                ],
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, AssistantMessage)
        assert len(msg.content) == 5
        assert isinstance(msg.content[0], ThinkingBlock)
        assert isinstance(msg.content[1], TextBlock)
        assert isinstance(msg.content[2], ToolUseBlock)
        assert isinstance(msg.content[3], ToolResultBlock)
        assert isinstance(msg.content[4], TextBlock)


class TestEdgeCasesAndValidation:
    """Test edge cases and validation."""

    def test_tool_result_with_none_content(self):
        """Test tool_result block with None content."""
        data = {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool_123",
                        "content": None,
                        "is_error": None,
                    }
                ]
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert msg.content[0].content is None
        assert msg.content[0].is_error is None

    def test_tool_result_with_list_content_complex(self):
        """Test tool_result with complex list content."""
        complex_content = [
            {"type": "image", "source": {"type": "url", "url": "data:image/png;base64,iVBOR..."}},
            {"type": "text", "text": "Image description"},
        ]
        data = {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool_456", "content": complex_content}
                ]
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert msg.content[0].content == complex_content

    def test_empty_tool_result_content(self):
        """Test tool_result with empty content string."""
        data = {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool_789",
                        "content": "",
                        "is_error": False,
                    }
                ]
            },
        }

        msg = parse_message(data)
        assert isinstance(msg, UserMessage)
        assert msg.content[0].content == ""
