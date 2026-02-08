"""Tests for Pydantic types in claude_sdk_lite.types module."""

import pytest

from claude_sdk_lite.types import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


class TestTextBlock:
    """Test TextBlock type."""

    def test_text_block_creation(self):
        """Test creating a TextBlock."""
        block = TextBlock(text="Hello, world!")
        assert block.text == "Hello, world!"
        assert block.type == "text"

    def test_text_block_serialization(self):
        """Test TextBlock JSON serialization."""
        block = TextBlock(text="Test")
        data = block.model_dump()
        assert data == {"text": "Test", "type": "text"}

    def test_text_block_default_type(self):
        """Test that type field defaults to 'text'."""
        block = TextBlock(text="Test")
        assert block.type == "text"


class TestThinkingBlock:
    """Test ThinkingBlock type."""

    def test_thinking_block_creation(self):
        """Test creating a ThinkingBlock."""
        block = ThinkingBlock(thinking="Let me think...", signature="abc123")
        assert block.thinking == "Let me think..."
        assert block.signature == "abc123"
        assert block.type == "thinking"

    def test_thinking_block_serialization(self):
        """Test ThinkingBlock JSON serialization."""
        block = ThinkingBlock(thinking="Thinking process", signature="sig456")
        data = block.model_dump()
        assert data["thinking"] == "Thinking process"
        assert data["signature"] == "sig456"
        assert data["type"] == "thinking"


class TestToolUseBlock:
    """Test ToolUseBlock type."""

    def test_tool_use_block_creation(self):
        """Test creating a ToolUseBlock."""
        block = ToolUseBlock(id="tool_123", name="bash", input={"command": "ls -la"})
        assert block.id == "tool_123"
        assert block.name == "bash"
        assert block.input == {"command": "ls -la"}
        assert block.type == "tool_use"

    def test_tool_use_block_with_complex_input(self):
        """Test ToolUseBlock with complex input dictionary."""
        block = ToolUseBlock(
            id="tool_456",
            name="Edit",
            input={"file_path": "test.py", "old_string": "old", "new_string": "new"},
        )
        assert block.input["file_path"] == "test.py"


class TestToolResultBlock:
    """Test ToolResultBlock type."""

    def test_tool_result_block_creation(self):
        """Test creating a ToolResultBlock."""
        block = ToolResultBlock(tool_use_id="tool_123", content="Success!")
        assert block.tool_use_id == "tool_123"
        assert block.content == "Success!"
        assert block.is_error is None
        assert block.type == "tool_result"

    def test_tool_result_block_with_error(self):
        """Test ToolResultBlock with error flag."""
        block = ToolResultBlock(tool_use_id="tool_123", content="Failed!", is_error=True)
        assert block.is_error is True

    def test_tool_result_block_with_list_content(self):
        """Test ToolResultBlock with list content."""
        content = [
            {"type": "text", "text": "Output line 1"},
            {"type": "text", "text": "Output line 2"},
        ]
        block = ToolResultBlock(tool_use_id="tool_123", content=content)
        assert block.content == content

    def test_tool_result_block_serialization(self):
        """Test ToolResultBlock JSON serialization."""
        block = ToolResultBlock(tool_use_id="tool_789", content="Result", is_error=False)
        data = block.model_dump()
        assert data["tool_use_id"] == "tool_789"
        assert data["content"] == "Result"
        assert data["is_error"] is False


class TestUserMessage:
    """Test UserMessage type."""

    def test_user_message_with_string_content(self):
        """Test UserMessage with string content."""
        msg = UserMessage(content="What is the capital of France?")
        assert msg.content == "What is the capital of France?"
        assert msg.uuid is None
        assert msg.parent_tool_use_id is None

    def test_user_message_with_list_content(self):
        """Test UserMessage with list of content blocks."""
        blocks = [
            TextBlock(text="Please run this command."),
            ToolUseBlock(id="tool_1", name="bash", input={"command": "npm test"}),
        ]
        msg = UserMessage(content=blocks)
        assert isinstance(msg.content, list)
        assert len(msg.content) == 2

    def test_user_message_with_optional_fields(self):
        """Test UserMessage with optional fields."""
        msg = UserMessage(
            content="Test",
            uuid="user-uuid-123",
            parent_tool_use_id="tool_parent",
            tool_use_result={"status": "completed"},
        )
        assert msg.uuid == "user-uuid-123"
        assert msg.parent_tool_use_id == "tool_parent"
        assert msg.tool_use_result == {"status": "completed"}


class TestAssistantMessage:
    """Test AssistantMessage type."""

    def test_assistant_message_creation(self):
        """Test creating an AssistantMessage."""
        content = [
            TextBlock(text="Hello!"),
        ]
        msg = AssistantMessage(content=content, model="claude-sonnet-4-5")
        assert msg.content == content
        assert msg.model == "claude-sonnet-4-5"
        assert msg.parent_tool_use_id is None
        assert msg.error is None

    def test_assistant_message_with_thinking(self):
        """Test AssistantMessage with thinking block."""
        content = [
            ThinkingBlock(thinking="Thinking...", signature="sig1"),
            TextBlock(text="Response"),
        ]
        msg = AssistantMessage(content=content, model="claude-sonnet-4-5")
        assert len(msg.content) == 2
        assert isinstance(msg.content[0], ThinkingBlock)
        assert isinstance(msg.content[1], TextBlock)

    def test_assistant_message_with_tool_use(self):
        """Test AssistantMessage with tool use."""
        content = [
            TextBlock(text="I'll help you."),
            ToolUseBlock(id="tool_1", name="bash", input={"command": "ls"}),
        ]
        msg = AssistantMessage(content=content, model="claude-sonnet-4-5")
        assert len(msg.content) == 2
        assert msg.content[1].name == "bash"

    def test_assistant_message_with_error(self):
        """Test AssistantMessage with error field."""
        msg = AssistantMessage(
            content=[TextBlock(text="Error occurred")],
            model="claude-sonnet-4-5",
            error="Tool execution failed",
        )
        assert msg.error == "Tool execution failed"


class TestSystemMessage:
    """Test SystemMessage type."""

    def test_system_message_creation(self):
        """Test creating a SystemMessage."""
        msg = SystemMessage(subtype="config", data={"setting": "value", "enabled": True})
        assert msg.subtype == "config"
        assert msg.data == {"setting": "value", "enabled": True}

    def test_system_message_status(self):
        """Test SystemMessage with status subtype."""
        msg = SystemMessage(subtype="status", data={"status": "ready", "session_id": "sess-123"})
        assert msg.subtype == "status"
        assert msg.data["status"] == "ready"


class TestResultMessage:
    """Test ResultMessage type."""

    def test_result_message_creation(self):
        """Test creating a ResultMessage."""
        msg = ResultMessage(
            subtype="complete",
            duration_ms=1500,
            duration_api_ms=1200,
            is_error=False,
            num_turns=3,
            session_id="sess-abc-123",
        )
        assert msg.subtype == "complete"
        assert msg.duration_ms == 1500
        assert msg.duration_api_ms == 1200
        assert msg.is_error is False
        assert msg.num_turns == 3
        assert msg.session_id == "sess-abc-123"
        assert msg.total_cost_usd is None

    def test_result_message_with_cost(self):
        """Test ResultMessage with cost information."""
        msg = ResultMessage(
            subtype="complete",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="sess-123",
            total_cost_usd=0.00123,
        )
        assert msg.total_cost_usd == 0.00123

    def test_result_message_with_usage(self):
        """Test ResultMessage with usage information."""
        msg = ResultMessage(
            subtype="complete",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="sess-123",
            usage={"input_tokens": 100, "output_tokens": 50, "cache_creation_tokens": 0},
        )
        assert msg.usage["input_tokens"] == 100
        assert msg.usage["output_tokens"] == 50

    def test_result_message_with_error(self):
        """Test ResultMessage indicating an error."""
        msg = ResultMessage(
            subtype="error",
            duration_ms=500,
            duration_api_ms=200,
            is_error=True,
            num_turns=0,
            session_id="sess-error-123",
            result="API request failed: timeout",
        )
        assert msg.is_error is True
        assert msg.result == "API request failed: timeout"

    def test_result_message_with_structured_output(self):
        """Test ResultMessage with structured output."""
        output = {"name": "Claude", "version": "4.5", "capabilities": ["code", "analysis"]}
        msg = ResultMessage(
            subtype="complete",
            duration_ms=2000,
            duration_api_ms=1800,
            is_error=False,
            num_turns=1,
            session_id="sess-123",
            structured_output=output,
        )
        assert msg.structured_output == output


class TestStreamEvent:
    """Test StreamEvent type."""

    def test_stream_event_creation(self):
        """Test creating a StreamEvent."""
        event = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}}
        msg = StreamEvent(uuid="msg-uuid-123", session_id="sess-123", event=event)
        assert msg.uuid == "msg-uuid-123"
        assert msg.session_id == "sess-123"
        assert msg.event == event
        assert msg.parent_tool_use_id is None

    def test_stream_event_with_parent_tool_use_id(self):
        """Test StreamEvent with parent_tool_use_id."""
        msg = StreamEvent(
            uuid="msg-uuid-456",
            session_id="sess-456",
            event={"type": "tool_call_delta"},
            parent_tool_use_id="tool_parent",
        )
        assert msg.parent_tool_use_id == "tool_parent"


class TestTypeValidation:
    """Test Pydantic validation behavior."""

    def test_text_block_requires_text(self):
        """Test that TextBlock requires text field."""
        with pytest.raises(ValueError):
            TextBlock()

    def test_thinking_block_requires_all_fields(self):
        """Test that ThinkingBlock requires thinking and signature."""
        with pytest.raises(ValueError):
            ThinkingBlock(thinking="test")  # Missing signature

        with pytest.raises(ValueError):
            ThinkingBlock(signature="sig123")  # Missing thinking

    def test_tool_use_block_required_fields(self):
        """Test that ToolUseBlock requires id, name, and input."""
        with pytest.raises(ValueError):
            ToolUseBlock(id="test", name="bash")  # Missing input

    def test_result_message_required_fields(self):
        """Test that ResultMessage requires all fields."""
        with pytest.raises(ValueError):
            ResultMessage(
                subtype="complete",
                duration_ms=1000,
                # Missing other required fields
            )
