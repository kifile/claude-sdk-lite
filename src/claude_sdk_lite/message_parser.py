"""Message parser for Claude SDK Lite responses."""

import json
import logging
from typing import Any

from .types import (
    AssistantMessage,
    ContentBlock,
    ControlResponseMessage,
    InterruptBlock,
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

logger = logging.getLogger(__name__)


class MessageParseError(Exception):
    """Error raised when message parsing fails.

    Note: parse_message() no longer raises this exception. Instead, it returns
    an UnknownMessage for any parsing failures. This exception is kept for
    backward compatibility but is no longer used internally.
    """

    def __init__(self, message: str, data: Any):
        self.message = message
        self.data = data
        super().__init__(f"{message}: {data}")


def parse_message(data: dict[str, Any] | str) -> Message:
    """
    Parse message from CLI output into typed Message objects.

    This function never raises exceptions for parsing errors. Instead, it returns
    an UnknownMessage containing the raw data, allowing the application layer to
    decide how to handle unexpected or malformed messages. This design provides
    forward compatibility and resilience.

    Args:
        data: Raw message dictionary from CLI output (dict or JSON string)

    Returns:
        Parsed Message object, or UnknownMessage if parsing fails

    Example:
        ```python
        raw = '{"type": "assistant", "message": {"model": "sonnet", "content": [...]}}'
        msg = parse_message(raw)
        isinstance(msg, AssistantMessage)  # True

        # Unknown types are safely wrapped:
        unknown_raw = '{"type": "future_type", "data": {...}}'
        msg = parse_message(unknown_raw)
        isinstance(msg, UnknownMessage)  # True
        msg.type == "future_type"  # True
        ```
    """
    # Parse JSON string if needed
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON string, returning UnknownMessage: {e}")
            return UnknownMessage(type="invalid_json", raw_data={"raw_string": data})

    if not isinstance(data, dict):
        logger.warning(
            f"Invalid message data type (expected dict, got {type(data).__name__}), returning UnknownMessage"
        )
        return UnknownMessage(
            type=f"invalid_type_{type(data).__name__}",
            raw_data={"raw_data": data} if not isinstance(data, str) else {"raw_string": data},
        )

    message_type = data.get("type")
    if not message_type:
        logger.debug("Message missing 'type' field, returning UnknownMessage")
        return UnknownMessage(type="missing_type", raw_data=data)

    # Try to parse known message types
    try:
        match message_type:
            case "user":
                return _parse_user_message(data)
            case "assistant":
                return _parse_assistant_message(data)
            case "system":
                return _parse_system_message(data)
            case "result":
                return _parse_result_message(data)
            case "stream_event":
                return _parse_stream_event(data)
            case "control_response":
                return _parse_control_response(data)
            case _:
                # Return UnknownMessage for unrecognized types for forward compatibility
                logger.debug(f"Unknown message type: {message_type}, returning UnknownMessage")
                return UnknownMessage(type=message_type, raw_data=data)
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        # Catch parsing errors and return UnknownMessage instead of raising
        logger.warning(f"Failed to parse {message_type} message: {e}, returning UnknownMessage")
        return UnknownMessage(type=message_type, raw_data=data)
    except Exception as e:
        # Catch any other unexpected exceptions
        logger.error(
            f"Unexpected error parsing {message_type} message: {e}, returning UnknownMessage"
        )
        return UnknownMessage(type=message_type, raw_data=data)


def _parse_content_blocks(blocks: list[dict[str, Any]]) -> list[ContentBlock]:
    """Parse content blocks from message data.

    Args:
        blocks: List of content block dictionaries

    Returns:
        List of parsed ContentBlock objects
    """
    content_blocks: list[ContentBlock] = []
    for block in blocks:
        match block["type"]:
            case "text":
                content_blocks.append(TextBlock(text=block["text"]))
            case "thinking":
                content_blocks.append(
                    ThinkingBlock(
                        thinking=block["thinking"],
                        signature=block["signature"],
                    )
                )
            case "tool_use":
                content_blocks.append(
                    ToolUseBlock(
                        id=block["id"],
                        name=block["name"],
                        input=block["input"],
                    )
                )
            case "tool_result":
                content_blocks.append(
                    ToolResultBlock(
                        tool_use_id=block["tool_use_id"],
                        content=block.get("content"),
                        is_error=block.get("is_error"),
                    )
                )
            case "interrupt":
                content_blocks.append(InterruptBlock())
    return content_blocks


def _parse_user_message(data: dict[str, Any]) -> UserMessage:
    """Parse a user message."""
    parent_tool_use_id = data.get("parent_tool_use_id")
    tool_use_result = data.get("tool_use_result")
    uuid = data.get("uuid")

    # Check if content is a list of blocks
    if isinstance(data["message"]["content"], list):
        user_content_blocks = _parse_content_blocks(data["message"]["content"])
        return UserMessage(
            content=user_content_blocks,
            uuid=uuid,
            parent_tool_use_id=parent_tool_use_id,
            tool_use_result=tool_use_result,
        )

    # Simple string content
    return UserMessage(
        content=data["message"]["content"],
        uuid=uuid,
        parent_tool_use_id=parent_tool_use_id,
        tool_use_result=tool_use_result,
    )


def _parse_assistant_message(data: dict[str, Any]) -> AssistantMessage:
    """Parse an assistant message."""
    content_blocks = _parse_content_blocks(data["message"]["content"])

    return AssistantMessage(
        content=content_blocks,
        model=data["message"]["model"],
        parent_tool_use_id=data.get("parent_tool_use_id"),
        error=data.get("error"),
    )


def _parse_system_message(data: dict[str, Any]) -> SystemMessage:
    """Parse a system message."""
    return SystemMessage(
        subtype=data["subtype"],
        data=data,
    )


def _parse_result_message(data: dict[str, Any]) -> ResultMessage:
    """Parse a result message."""
    return ResultMessage(
        subtype=data["subtype"],
        duration_ms=data["duration_ms"],
        duration_api_ms=data["duration_api_ms"],
        is_error=data["is_error"],
        num_turns=data["num_turns"],
        session_id=data["session_id"],
        total_cost_usd=data.get("total_cost_usd"),
        usage=data.get("usage"),
        result=data.get("result"),
        structured_output=data.get("structured_output"),
    )


def _parse_stream_event(data: dict[str, Any]) -> StreamEvent:
    """Parse a stream event."""
    return StreamEvent(
        uuid=data["uuid"],
        session_id=data["session_id"],
        event=data["event"],
        parent_tool_use_id=data.get("parent_tool_use_id"),
    )


def _parse_control_response(data: dict[str, Any]) -> ControlResponseMessage:
    """Parse a control response message."""
    response_data = data.get("response", {})
    return ControlResponseMessage(
        subtype=response_data.get("subtype", "unknown"),
        request_id=response_data.get("request_id"),
        response=response_data,
    )
