"""Tests for async query function with mocked subprocess."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from claude_sdk_lite import ClaudeOptions
from claude_sdk_lite.query import (
    CLIExecutionError,
    CLINotFoundError,
)
from claude_sdk_lite.query import async_query as query
from claude_sdk_lite.query import async_query_text as query_text
from claude_sdk_lite.types import AssistantMessage, ResultMessage


class AsyncIteratorMock:
    """Mock async iterator."""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


@pytest.fixture
def mock_cli_response():
    """Create a mock CLI process with given responses."""

    def _create(responses, returncode=0):
        mock_process = AsyncMock()
        mock_process.returncode = returncode
        mock_process.wait = AsyncMock(return_value=returncode)
        mock_process.stderr = AsyncMock()

        # Create a list of encoded responses
        lines = [json.dumps(r).encode() + b"\n" for r in responses]

        # Create async iterator mock
        mock_process.stdout = AsyncIteratorMock(lines)
        return mock_process

    return _create


@pytest.mark.asyncio
class TestAsyncQueryFunction:
    """Test the async query() function."""

    async def test_query_simple_success(self, mock_cli_response):
        """Test successful query with simple response."""
        responses = [
            {
                "type": "assistant",
                "message": {"model": "sonnet", "content": [{"type": "text", "text": "Hello!"}]},
            }
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = []
            async for msg in query(prompt="Hi"):
                messages.append(msg)

            assert len(messages) == 1
            assert isinstance(messages[0], AssistantMessage)
            assert messages[0].content[0].text == "Hello!"

    async def test_query_with_thinking(self, mock_cli_response):
        """Test query with thinking blocks."""
        responses = [
            {
                "type": "assistant",
                "message": {
                    "model": "sonnet",
                    "content": [
                        {"type": "thinking", "thinking": "Let me think...", "signature": "sig123"},
                        {"type": "text", "text": "The answer is 42."},
                    ],
                },
            },
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 1000,
                "duration_api_ms": 800,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            },
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = []
            async for msg in query(prompt="What is the meaning of life?"):
                messages.append(msg)

            assert len(messages) == 2
            assert isinstance(messages[0], AssistantMessage)
            assert len(messages[0].content) == 2
            assert isinstance(messages[1], ResultMessage)

    async def test_query_with_tool_use(self, mock_cli_response):
        """Test query that uses tools."""
        responses = [
            {
                "type": "assistant",
                "message": {
                    "model": "sonnet",
                    "content": [
                        {"type": "text", "text": "I'll list the files."},
                        {
                            "type": "tool_use",
                            "id": "tool_1",
                            "name": "bash",
                            "input": {"command": "ls"},
                        },
                    ],
                },
            }
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = []
            async for msg in query(prompt="List files"):
                messages.append(msg)

            assert len(messages) == 1
            assert len(messages[0].content) == 2
            assert messages[0].content[1].name == "bash"

    async def test_query_with_custom_options(self, mock_cli_response):
        """Test query with custom options."""
        responses = [
            {
                "type": "assistant",
                "message": {
                    "model": "haiku",
                    "content": [{"type": "text", "text": "Quick response"}],
                },
            }
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_subprocess:
            options = ClaudeOptions(model="haiku", max_turns=1, system_prompt="Be concise")

            async for msg in query(prompt="Quick question", options=options):
                pass

            # Verify subprocess was called with correct arguments
            call_args = mock_subprocess.call_args[0]
            assert "--model" in call_args
            assert "haiku" in call_args
            assert "--max-turns" in call_args
            assert "1" in call_args
            assert "--system-prompt" in call_args
            assert "Be concise" in call_args

    async def test_query_cli_not_found(self):
        """Test query when CLI is not found."""
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            with pytest.raises(CLINotFoundError, match="Claude Code CLI not found"):
                async for msg in query(prompt="test"):
                    pass

    async def test_query_cli_execution_error(self):
        """Test query when CLI execution fails."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.wait = AsyncMock(return_value=1)
        mock_process.stderr = AsyncMock()
        mock_process.stderr.read = AsyncMock(return_value=b"Error: Invalid option\n")
        mock_process.stdout = AsyncIteratorMock([])

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(CLIExecutionError, match="CLI exited with code 1"):
                async for msg in query(prompt="test"):
                    pass

    async def test_query_stops_at_result_message(self, mock_cli_response):
        """Test that query stops iteration at result message."""
        responses = [
            {
                "type": "assistant",
                "message": {"model": "sonnet", "content": [{"type": "text", "text": "Response"}]},
            },
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 1000,
                "duration_api_ms": 800,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            },
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = []
            async for msg in query(prompt="test"):
                messages.append(msg)

            assert len(messages) == 2
            assert isinstance(messages[1], ResultMessage)

    async def test_query_uses_default_options(self, mock_cli_response):
        """Test that query uses default options when none provided."""
        responses = [
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 100,
                "duration_api_ms": 50,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            }
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_subprocess:
            async for msg in query(prompt="test"):
                pass

            call_args = mock_subprocess.call_args[0]
            assert "--print" in call_args
            assert "--output-format" in call_args
            assert "stream-json" in call_args

    async def test_query_with_working_dir(self, mock_cli_response):
        """Test query with custom working directory."""
        responses = [
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 100,
                "duration_api_ms": 50,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            }
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_subprocess:
            options = ClaudeOptions(working_dir="/custom/path")
            async for msg in query(prompt="test", options=options):
                pass

            call_kwargs = mock_subprocess.call_args[1]
            assert "cwd" in call_kwargs
            assert call_kwargs["cwd"] == "/custom/path"

    async def test_query_with_env_vars(self, mock_cli_response):
        """Test query with custom environment variables."""
        responses = [
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 100,
                "duration_api_ms": 50,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            }
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_subprocess:
            options = ClaudeOptions(env={"CUSTOM_VAR": "custom_value"})
            async for msg in query(prompt="test", options=options):
                pass

            call_kwargs = mock_subprocess.call_args[1]
            assert "env" in call_kwargs
            assert call_kwargs["env"]["CUSTOM_VAR"] == "custom_value"


@pytest.mark.asyncio
class TestAsyncQueryTextFunction:
    """Test the async query_text() convenience function."""

    async def test_query_text_simple(self, mock_cli_response):
        """Test query_text with simple response."""
        responses = [
            {
                "type": "assistant",
                "message": {"model": "sonnet", "content": [{"type": "text", "text": "Hello!"}]},
            },
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 100,
                "duration_api_ms": 50,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            },
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await query_text(prompt="Say hello")
            assert result == "Hello!"

    async def test_query_text_multiple_blocks(self, mock_cli_response):
        """Test query_text concatenates multiple text blocks."""
        responses = [
            {
                "type": "assistant",
                "message": {
                    "model": "sonnet",
                    "content": [
                        {"type": "text", "text": "First part. "},
                        {"type": "text", "text": "Second part."},
                    ],
                },
            },
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 100,
                "duration_api_ms": 50,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            },
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await query_text(prompt="Test")
            assert result == "First part. Second part."

    async def test_query_text_ignores_thinking(self, mock_cli_response):
        """Test query_text ignores thinking blocks."""
        responses = [
            {
                "type": "assistant",
                "message": {
                    "model": "sonnet",
                    "content": [
                        {"type": "thinking", "thinking": "Internal thought", "signature": "sig"},
                        {"type": "text", "text": "Actual response"},
                    ],
                },
            },
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 100,
                "duration_api_ms": 50,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            },
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await query_text(prompt="Test")
            assert result == "Actual response"

    async def test_query_text_with_options(self, mock_cli_response):
        """Test query_text with custom options."""
        responses = [
            {
                "type": "assistant",
                "message": {
                    "model": "haiku",
                    "content": [{"type": "text", "text": "Quick response"}],
                },
            },
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 100,
                "duration_api_ms": 50,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            },
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_subprocess:
            options = ClaudeOptions(model="haiku")
            result = await query_text(prompt="Test", options=options)

            call_args = mock_subprocess.call_args[0]
            assert "haiku" in call_args
            assert result == "Quick response"

    async def test_query_text_empty_response(self, mock_cli_response):
        """Test query_text with no text content."""
        responses = [
            {
                "type": "assistant",
                "message": {
                    "model": "sonnet",
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
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 100,
                "duration_api_ms": 50,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            },
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await query_text(prompt="Test")
            assert result == ""

    async def test_query_text_handles_errors(self):
        """Test query_text propagates errors."""
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            with pytest.raises(CLINotFoundError):
                await query_text(prompt="Test")


@pytest.mark.asyncio
class TestAsyncRealWorldScenarios:
    """Test real-world usage scenarios with async query."""

    async def test_code_generation_workflow(self, mock_cli_response):
        """Test a typical code generation workflow."""
        responses = [
            {
                "type": "assistant",
                "message": {
                    "model": "sonnet",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "Need to create a function",
                            "signature": "sig1",
                        },
                        {"type": "text", "text": "I'll create a hello world function."},
                    ],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "model": "sonnet",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tool_1",
                            "name": "Write",
                            "input": {
                                "file_path": "hello.py",
                                "content": "def hello():\n    print('Hello!')",
                            },
                        }
                    ],
                },
            },
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 2000,
                "duration_api_ms": 1500,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-code-123",
                "total_cost_usd": 0.002,
            },
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = []
            async for msg in query(prompt="Create a hello world function"):
                messages.append(msg)

            assert len(messages) == 3
            assert isinstance(messages[0], AssistantMessage)
            assert isinstance(messages[1], AssistantMessage)
            assert isinstance(messages[2], ResultMessage)
            assert messages[2].total_cost_usd == 0.002

    async def test_error_recovery_scenario(self):
        """Test error scenario with CLI execution error."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.wait = AsyncMock(return_value=1)
        mock_process.stderr = AsyncMock()
        mock_process.stderr.read = AsyncMock(return_value=b"Error: API rate limit exceeded\n")
        mock_process.stdout = AsyncIteratorMock([])

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(CLIExecutionError) as exc_info:
                async for msg in query(prompt="test"):
                    pass

            assert exc_info.value.exit_code == 1
            assert "API rate limit" in str(exc_info.value.stderr)


@pytest.mark.asyncio
class TestAsyncQueryStreaming:
    """Test async query streaming behavior."""

    async def test_query_streams_messages_incrementally(self, mock_cli_response):
        """Test that query yields messages as they arrive."""
        responses = [
            {
                "type": "assistant",
                "message": {"model": "sonnet", "content": [{"type": "text", "text": "First"}]},
            },
            {
                "type": "assistant",
                "message": {"model": "sonnet", "content": [{"type": "text", "text": "Second"}]},
            },
            {
                "type": "assistant",
                "message": {"model": "sonnet", "content": [{"type": "text", "text": "Third"}]},
            },
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 1000,
                "duration_api_ms": 800,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            },
        ]
        mock_process = mock_cli_response(responses)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            message_count = 0
            async for msg in query(prompt="Test"):
                message_count += 1
                if message_count < 4:  # First 3 are assistant messages
                    assert isinstance(msg, AssistantMessage)
                else:  # Last is result
                    assert isinstance(msg, ResultMessage)

            assert message_count == 4

    async def test_query_handles_malformed_json(self, mock_cli_response):
        """Test that query handles malformed JSON gracefully by skipping invalid lines."""

        # Create mock with some valid and some invalid JSON
        class MockStdoutWithInvalid:
            def __init__(self, items):
                self.items = items
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.items):
                    raise StopAsyncIteration
                item = self.items[self.index]
                self.index += 1
                return item

        responses = [
            {
                "type": "assistant",
                "message": {"model": "sonnet", "content": [{"type": "text", "text": "Valid"}]},
            },
            b"invalid json line",
            {
                "type": "result",
                "subtype": "complete",
                "duration_ms": 1000,
                "duration_api_ms": 800,
                "is_error": False,
                "num_turns": 1,
                "session_id": "sess-123",
            },
        ]

        lines = [
            json.dumps(responses[0]).encode(),
            responses[1],
            json.dumps(responses[2]).encode(),
        ]

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stdout = MockStdoutWithInvalid(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = []
            async for msg in query(prompt="test"):
                messages.append(msg)

            # Should skip invalid JSON and return only valid messages
            assert len(messages) == 2
            assert isinstance(messages[0], AssistantMessage)
            assert isinstance(messages[1], ResultMessage)
