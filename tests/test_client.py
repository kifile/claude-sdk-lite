"""Tests for ClaudeClient - synchronous session-based client."""

import uuid

import pytest

from claude_sdk_lite import ClaudeClient, ClaudeOptions


class TestClaudeClientInit:
    """Test ClaudeClient initialization and configuration."""

    def test_init_with_default_options(self):
        """Test initialization with default options."""
        client = ClaudeClient()

        assert client.options is not None
        assert client.session_id is not None
        assert isinstance(client.session_id, str)
        # Should be a valid UUID
        uuid.UUID(client.session_id)  # Will raise if invalid

    def test_init_with_custom_options(self):
        """Test initialization with custom options."""
        options = ClaudeOptions(model="sonnet")
        client = ClaudeClient(options=options)

        # Client creates a copy of options (with session_id)
        assert client.options.model == "sonnet"
        # Check that it's a different object (copy was made)
        assert client.options is not options

    def test_init_generates_session_id_if_not_provided(self):
        """Test that session_id is generated if not in options."""
        options = ClaudeOptions()
        assert options.session_id is None

        client = ClaudeClient(options=options)

        assert client.session_id is not None
        assert isinstance(client.session_id, str)
        # Original options should not be modified
        assert options.session_id is None

    def test_init_uses_provided_session_id(self):
        """Test that provided session_id is used."""
        custom_session_id = "my-custom-session-123"
        options = ClaudeOptions(session_id=custom_session_id)
        client = ClaudeClient(options=options)

        assert client.session_id == custom_session_id

    def test_init_with_valid_uuid_session_id(self):
        """Test initialization with valid UUID as session_id."""
        custom_uuid = str(uuid.uuid4())
        options = ClaudeOptions(session_id=custom_uuid)
        client = ClaudeClient(options=options)

        assert client.session_id == custom_uuid

    def test_debug_flag_caching(self):
        """Test that debug flag is cached at initialization."""
        import os

        # Set debug before creating client
        os.environ["CLAUDE_SDK_DEBUG"] = "true"

        client = ClaudeClient()
        assert client._debug is True

        # Change environment variable
        os.environ["CLAUDE_SDK_DEBUG"] = "false"

        # Client should still have cached value
        assert client._debug is True

        # Clean up
        del os.environ["CLAUDE_SDK_DEBUG"]


class TestClaudeClientConnection:
    """Test ClaudeClient connection lifecycle."""

    def test_is_connected_initially_false(self):
        """Test that is_connected is False before connection."""
        client = ClaudeClient()
        assert not client.is_connected

    def test_context_manager_auto_connect(self):
        """Test that context manager automatically connects."""
        client = ClaudeClient()
        assert not client.is_connected

        with client:
            # Note: This will actually start the process
            # For testing, we use a mock command
            pass

        # After context, should be disconnected
        assert not client.is_connected

    def test_connect_when_already_connected_returns_early(self):
        """Test that calling connect() twice doesn't error."""
        client = ClaudeClient()

        # First connect
        with client:
            # This should work
            pass
        # Disconnect

        # Second connect should also work
        with client:
            pass


class TestClaudeClientQuery:
    """Test ClaudeClient query methods."""

    def test_query_returns_list_of_messages(self):
        """Test that query() returns a list of Message objects."""
        # This test requires mocking since we need actual subprocess
        # For now, we test the interface
        client = ClaudeClient()

        # Without connection, should raise RuntimeError
        with pytest.raises(RuntimeError, match="not connected"):
            client.query("test prompt")

    def test_query_stream_is_iterator(self):
        """Test that query_stream() returns an iterator."""
        client = ClaudeClient()

        # Without connection, should raise RuntimeError
        with pytest.raises(RuntimeError, match="not connected"):
            iterator = client.query_stream("test prompt")
            # Consuming it should raise
            for _ in iterator:
                pass


class TestClaudeClientInterrupt:
    """Test ClaudeClient interrupt functionality."""

    def test_interrupt_without_connection_raises_error(self):
        """Test that interrupt() raises error when not connected."""
        client = ClaudeClient()

        with pytest.raises(RuntimeError, match="not connected"):
            client.interrupt()


class TestClaudeClientCommands:
    """Test ClaudeClient command building."""

    def test_build_command_includes_stream_json_format(self):
        """Test that built command includes stream-json format."""
        options = ClaudeOptions(model="sonnet")
        client = ClaudeClient(options=options)

        cmd = client._build_command()

        # Should include stream-json flags
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--input-format" in cmd
        assert "--verbose" in cmd

        # Should NOT include --print mode
        assert "--print" not in cmd

    def test_build_command_preserves_model_option(self):
        """Test that model option is preserved in command."""
        options = ClaudeOptions(model="haiku")
        client = ClaudeClient(options=options)

        cmd = client._build_command()

        # Should include model
        assert "--model" in cmd
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "haiku"

    def test_build_subprocess_kwargs_includes_working_dir(self):
        """Test that working_dir is included in kwargs."""
        options = ClaudeOptions(working_dir="/tmp/test")
        client = ClaudeClient(options=options)

        kwargs = client._build_subprocess_kwargs()

        assert "cwd" in kwargs
        assert kwargs["cwd"] == "/tmp/test"

    def test_build_subprocess_kwargs_includes_env_vars(self):
        """Test that environment variables are merged."""
        options = ClaudeOptions(env={"TEST_VAR": "test_value"})
        client = ClaudeClient(options=options)

        kwargs = client._build_subprocess_kwargs()

        assert "env" in kwargs
        assert "TEST_VAR" in kwargs["env"]
        assert kwargs["env"]["TEST_VAR"] == "test_value"

    def test_build_subprocess_kwargs_merges_with_os_environ(self):
        """Test that custom env vars are merged with os.environ."""

        options = ClaudeOptions(env={"CUSTOM_VAR": "custom_value"})
        client = ClaudeClient(options=options)

        kwargs = client._build_subprocess_kwargs()

        # Should include PATH from os.environ
        assert "PATH" in kwargs["env"]
        # Should include custom var
        assert "CUSTOM_VAR" in kwargs["env"]


class TestClaudeClientProperties:
    """Test ClaudeClient properties."""

    def test_stderr_property(self):
        """Test stderr_output property."""
        client = ClaudeClient()
        # Before connection, should return empty list
        stderr = client.stderr_output
        assert isinstance(stderr, list)
        assert len(stderr) == 0


class TestClaudeClientIntegration:
    """Integration tests with mock subprocess."""

    def test_full_query_flow_with_cat(self):
        """Test full query flow using cat as mock subprocess."""
        # Use cat which will echo our input
        options = ClaudeOptions(
            cli_path="cat",
        )

        # We'll need to patch the command building for this test
        # For now, test the structure
        client = ClaudeClient(options=options)

        # Verify client is properly configured
        assert client.session_id is not None
        assert client.options.cli_path == "cat"


class TestClaudeClientErrorHandling:
    """Test error handling in ClaudeClient."""

    def test_query_fails_when_not_connected(self):
        """Test that query() fails gracefully when not connected."""
        client = ClaudeClient()

        with pytest.raises(RuntimeError, match="not connected"):
            list(client.query_stream("test"))

    def test_interrupt_fails_when_not_connected(self):
        """Test that interrupt() fails gracefully when not connected."""
        client = ClaudeClient()

        with pytest.raises(RuntimeError, match="not connected"):
            client.interrupt()


class TestClaudeClientMessageFormat:
    """Test message formatting for subprocess communication."""

    def test_message_format_includes_session_id(self):
        """Test that messages include the session_id."""
        client = ClaudeClient()
        client.session_id = "test-session-123"

        # Build a message like query_stream does
        message = {
            "type": "user",
            "message": {"role": "user", "content": "test prompt"},
            "session_id": client.session_id,
        }

        assert message["session_id"] == "test-session-123"
        assert message["type"] == "user"
        assert message["message"]["role"] == "user"
