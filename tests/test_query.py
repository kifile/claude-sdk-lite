"""Tests for sync query function with mocked subprocess."""

import json
from unittest.mock import MagicMock, patch

import pytest

from claude_sdk_lite import (
    ClaudeOptions,
    CLIExecutionError,
    CLINotFoundError,
    query,
    query_text,
)
from claude_sdk_lite.types import AssistantMessage, ResultMessage


class MockProcess:
    """Mock subprocess.Popen object."""

    def __init__(self, stdout_lines=None, returncode=0, stderr=b""):
        self.stdout_lines = stdout_lines or []
        self.returncode = returncode
        self.stderr_data = stderr
        self._stdout_index = 0

        # Create mock stdout with proper iterator
        self.stdout = self._create_mock_stdout()

        # Create mock stderr
        self.stderr = MagicMock()
        self.stderr.read = MagicMock(return_value=self.stderr_data)

    def _create_mock_stdout(self):
        """Create a mock stdout that can be iterated."""

        class MockStdout:
            def __init__(self, lines):
                self.lines = lines
                self.index = 0

            def __iter__(self):
                return self

            def __next__(self):
                if self.index >= len(self.lines):
                    raise StopIteration
                line = self.lines[self.index]
                self.index += 1
                return line.encode() if isinstance(line, str) else line

            def read(self):
                return b"".join(
                    line.encode() if isinstance(line, str) else line for line in self.lines
                )

        return MockStdout(self.stdout_lines)

    def poll(self):
        """Check if process has terminated."""
        return None if self._stdout_index < len(self.stdout_lines) else self.returncode

    def wait(self, timeout=None):
        """Wait for process to complete."""
        self._stdout_index = len(self.stdout_lines)  # Mark as complete
        return self.returncode

    def terminate(self):
        """Terminate the process."""
        self._stdout_index = len(self.stdout_lines)

    def kill(self):
        """Kill the process."""
        self._stdout_index = len(self.stdout_lines)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        return False

    def communicate(self, input=None, timeout=None):
        """Communicate with process (for subprocess.run compatibility)."""
        stdout_data = b"".join(
            line.encode() if isinstance(line, str) else line for line in self.stdout_lines
        )
        return (stdout_data, self.stderr_data)


@pytest.fixture
def mock_subprocess_popen():
    """Create a mock subprocess.Popen function."""

    def _create(responses, returncode=0):
        """Create a mock process with given responses."""
        lines = [json.dumps(r) for r in responses]
        return MockProcess(stdout_lines=lines, returncode=returncode)

    return _create


@pytest.fixture(autouse=True)
def mock_find_cli():
    """Mock CLI finding to avoid actual subprocess.run calls in _find_cli_path."""
    with patch("claude_sdk_lite.utils.find_tool_in_system_sync", return_value="/usr/bin/claude"):
        yield


class TestQueryFunction:
    """Test the query() function."""

    def test_query_simple_success(self, mock_subprocess_popen):
        """Test successful query with simple response."""
        responses = [
            {
                "type": "assistant",
                "message": {"model": "sonnet", "content": [{"type": "text", "text": "Hello!"}]},
            }
        ]
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process):
            messages = []
            for msg in query(prompt="Hi"):
                messages.append(msg)

            assert len(messages) == 1
            assert isinstance(messages[0], AssistantMessage)
            assert messages[0].content[0].text == "Hello!"

    def test_query_with_thinking(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process):
            messages = []
            for msg in query(prompt="What is the meaning of life?"):
                messages.append(msg)

            assert len(messages) == 2
            assert isinstance(messages[0], AssistantMessage)
            assert len(messages[0].content) == 2
            assert isinstance(messages[1], ResultMessage)

    def test_query_with_tool_use(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process):
            messages = []
            for msg in query(prompt="List files"):
                messages.append(msg)

            assert len(messages) == 1
            assert len(messages[0].content) == 2
            assert messages[0].content[1].name == "bash"

    def test_query_with_custom_options(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            options = ClaudeOptions(model="haiku", max_turns=1, system_prompt="Be concise")

            for msg in query(prompt="Quick question", options=options):
                pass

            # Verify Popen was called with correct arguments
            call_args = mock_popen.call_args
            cmd = call_args[0][0]  # First positional arg (command list)
            assert "--model" in cmd
            assert "haiku" in cmd
            assert "--max-turns" in cmd
            assert "1" in cmd
            assert "--system-prompt" in cmd
            assert "Be concise" in cmd

    def test_query_cli_not_found(self):
        """Test query when CLI is not found."""
        with patch("claude_sdk_lite.utils.find_tool_in_system_sync", return_value=None):
            with pytest.raises(CLINotFoundError):
                for msg in query(prompt="test"):
                    pass

    def test_query_cli_execution_error(self):
        """Test query when CLI execution fails."""
        mock_process = MockProcess(stdout_lines=[], returncode=1, stderr=b"Error: Invalid option\n")

        with patch("subprocess.Popen", return_value=mock_process):
            with pytest.raises(CLIExecutionError, match="CLI exited with code 1"):
                for msg in query(prompt="test"):
                    pass

    def test_query_stops_at_result_message(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process):
            messages = []
            for msg in query(prompt="test"):
                messages.append(msg)

            assert len(messages) == 2
            assert isinstance(messages[1], ResultMessage)

    def test_query_uses_default_options(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            for msg in query(prompt="test"):
                pass

            call_args = mock_popen.call_args
            cmd = call_args[0][0]
            assert "--print" in cmd
            assert "--output-format" in cmd
            assert "stream-json" in cmd

    def test_query_with_working_dir(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            options = ClaudeOptions(working_dir="/custom/path")
            for msg in query(prompt="test", options=options):
                pass

            call_kwargs = mock_popen.call_args[1]
            assert "cwd" in call_kwargs
            assert call_kwargs["cwd"] == "/custom/path"

    def test_query_with_env_vars(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            options = ClaudeOptions(env={"CUSTOM_VAR": "custom_value"})
            for msg in query(prompt="test", options=options):
                pass

            call_kwargs = mock_popen.call_args[1]
            assert "env" in call_kwargs
            assert call_kwargs["env"]["CUSTOM_VAR"] == "custom_value"


class TestQueryTextFunction:
    """Test the query_text() convenience function."""

    def test_query_text_simple(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process):
            result = query_text(prompt="Say hello")
            assert result == "Hello!"

    def test_query_text_multiple_blocks(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process):
            result = query_text(prompt="Test")
            assert result == "First part. Second part."

    def test_query_text_ignores_thinking(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process):
            result = query_text(prompt="Test")
            assert result == "Actual response"

    def test_query_text_with_options(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            options = ClaudeOptions(model="haiku")
            result = query_text(prompt="Test", options=options)

            call_args = mock_popen.call_args
            cmd = call_args[0][0]
            assert "haiku" in cmd
            assert result == "Quick response"

    def test_query_text_empty_response(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process):
            result = query_text(prompt="Test")
            assert result == ""

    def test_query_text_handles_errors(self):
        """Test query_text propagates errors."""
        with patch("subprocess.Popen", side_effect=FileNotFoundError):
            with pytest.raises(CLINotFoundError):
                query_text(prompt="Test")


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_code_generation_workflow(self, mock_subprocess_popen):
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
        mock_process = mock_subprocess_popen(responses)

        with patch("subprocess.Popen", return_value=mock_process):
            messages = []
            for msg in query(prompt="Create a hello world function"):
                messages.append(msg)

            assert len(messages) == 3
            assert isinstance(messages[0], AssistantMessage)
            assert isinstance(messages[1], AssistantMessage)
            assert isinstance(messages[2], ResultMessage)
            assert messages[2].total_cost_usd == 0.002

    def test_error_recovery_scenario(self):
        """Test error scenario with CLI execution error."""
        mock_process = MockProcess(
            stdout_lines=[], returncode=1, stderr=b"Error: API rate limit exceeded\n"
        )

        with patch("subprocess.Popen", return_value=mock_process):
            with pytest.raises(CLIExecutionError) as exc_info:
                for msg in query(prompt="test"):
                    pass

            assert exc_info.value.exit_code == 1
            assert "API rate limit" in str(exc_info.value.stderr)
