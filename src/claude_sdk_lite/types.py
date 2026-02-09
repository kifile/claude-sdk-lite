"""Message types for Claude SDK Lite.

Compatible with official claude-agent-sdk message types.
"""

from typing import Any, Literal

from pydantic import BaseModel


class TextBlock(BaseModel):
    """Text content block."""

    text: str
    type: Literal["text"] = "text"


class ThinkingBlock(BaseModel):
    """Thinking content block (extended thinking)."""

    thinking: str
    signature: str
    type: Literal["thinking"] = "thinking"


class ToolUseBlock(BaseModel):
    """Tool use content block."""

    id: str
    name: str
    input: dict[str, Any]
    type: Literal["tool_use"] = "tool_use"


class ToolResultBlock(BaseModel):
    """Tool result content block."""

    tool_use_id: str
    content: str | list[dict[str, Any]] | None = None
    is_error: bool | None = None
    type: Literal["tool_result"] = "tool_result"


ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock


class UserMessage(BaseModel):
    """User message."""

    content: str | list[ContentBlock]
    uuid: str | None = None
    parent_tool_use_id: str | None = None
    tool_use_result: dict[str, Any] | None = None


class AssistantMessage(BaseModel):
    """Assistant message with content blocks.

    Example:
        ```python
        msg = AssistantMessage(
            content=[TextBlock(text="Hello!")],
            model="claude-sonnet-4-5"
        )
        ```
    """

    content: list[ContentBlock]
    model: str
    parent_tool_use_id: str | None = None
    error: str | None = None


class SystemMessage(BaseModel):
    """System message with metadata."""

    subtype: str
    data: dict[str, Any]


class ResultMessage(BaseModel):
    """Result message with cost and usage information.

    Example:
        ```python
        msg = ResultMessage(
            subtype="complete",
            duration_ms=1500,
            duration_api_ms=1200,
            is_error=False,
            num_turns=3,
            session_id="abc-123",
            total_cost_usd=0.001
        )
        ```
    """

    subtype: str
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    total_cost_usd: float | None = None
    usage: dict[str, Any] | None = None
    result: str | None = None
    structured_output: Any = None


class StreamEvent(BaseModel):
    """Stream event for partial message updates during streaming."""

    uuid: str
    session_id: str
    event: dict[str, Any]
    parent_tool_use_id: str | None = None


class UnknownMessage(BaseModel):
    """Unknown message type for forward compatibility.

    When encountering unrecognized message types, this allows the application
    to continue processing instead of failing. Users can inspect the raw data
    and decide how to handle these messages.

    Example:
        ```python
        msg = UnknownMessage(
            type="new_future_type",
            raw_data={"field": "value"}
        )
        if isinstance(msg, UnknownMessage):
            logger.warning(f"Unknown message type: {msg.type}")
        ```
    """

    type: str
    raw_data: dict[str, Any]


Message = (
    UserMessage
    | AssistantMessage
    | SystemMessage
    | ResultMessage
    | StreamEvent
    | UnknownMessage
)
