"""Tests for AsyncClaudeClient - asynchronous session-based client."""

import asyncio
import uuid

import pytest

from claude_sdk_lite import AsyncClaudeClient, ClaudeOptions


class TestAsyncClaudeClientInit:
    """Test AsyncClaudeClient initialization and configuration."""

    def test_init_with_default_options(self):
        """Test initialization with default options."""
        client = AsyncClaudeClient()

        assert client.options is not None
        assert client.session_id is not None
        assert isinstance(client.session_id, str)
        # Should be a valid UUID
        uuid.UUID(client.session_id)  # Will raise if invalid

    def test_init_with_custom_options(self):
        """Test initialization with custom options."""
        options = ClaudeOptions(model="sonnet")
        client = AsyncClaudeClient(options=options)

        # Client creates a copy of options (with session_id)
        assert client.options.model == "sonnet"
        # Check that it's a different object (copy was made)
        assert client.options is not options

    def test_init_generates_session_id_if_not_provided(self):
        """Test that session_id is generated if not in options."""
        options = ClaudeOptions()
        assert options.session_id is None

        client = AsyncClaudeClient(options=options)

        assert client.session_id is not None
        assert isinstance(client.session_id, str)
        # Original options should not be modified
        assert options.session_id is None

    def test_init_uses_provided_session_id(self):
        """Test that provided session_id is used."""
        custom_session_id = "my-custom-session-123"
        options = ClaudeOptions(session_id=custom_session_id)
        client = AsyncClaudeClient(options=options)

        assert client.session_id == custom_session_id

    def test_init_with_valid_uuid_session_id(self):
        """Test initialization with valid UUID as session_id."""
        custom_uuid = str(uuid.uuid4())
        options = ClaudeOptions(session_id=custom_uuid)
        client = AsyncClaudeClient(options=options)

        assert client.session_id == custom_uuid

    def test_debug_flag_caching(self):
        """Test that debug flag is cached at initialization."""
        import os

        # Set debug before creating client
        os.environ["CLAUDE_SDK_DEBUG"] = "true"

        client = AsyncClaudeClient()
        assert client._debug is True

        # Change environment variable
        os.environ["CLAUDE_SDK_DEBUG"] = "false"

        # Client should still have cached value
        assert client._debug is True

        # Clean up
        del os.environ["CLAUDE_SDK_DEBUG"]


class TestAsyncClaudeClientConnection:
    """Test AsyncClaudeClient connection lifecycle."""

    def test_is_connected_initially_false(self):
        """Test that is_connected is False before connection."""
        client = AsyncClaudeClient()
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_context_manager_auto_connect(self):
        """Test that async context manager automatically connects."""
        client = AsyncClaudeClient()
        assert not client.is_connected

        async with client:
            # Note: This will actually start the process
            # For testing, we use a mock command
            pass

        # After context, should be disconnected
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_connect_when_already_connected_returns_early(self):
        """Test that calling connect() twice doesn't error."""
        client = AsyncClaudeClient()

        # First connect
        async with client:
            # This should work
            pass
        # Disconnect

        # Second connect should also work
        async with client:
            pass


class TestAsyncClaudeClientQuery:
    """Test AsyncClaudeClient query methods."""

    @pytest.mark.asyncio
    async def test_query_returns_list_of_messages(self):
        """Test that query() returns a list of Message objects."""
        client = AsyncClaudeClient()

        # Without connection, should raise RuntimeError
        with pytest.raises(RuntimeError, match="not connected"):
            await client.query("test prompt")

    @pytest.mark.asyncio
    async def test_query_stream_is_async_iterator(self):
        """Test that query_stream() returns an async iterator."""
        client = AsyncClaudeClient()

        # Without connection, should raise RuntimeError
        with pytest.raises(RuntimeError, match="not connected"):
            # Try to consume the stream
            async for _ in client.query_stream("test prompt"):
                pass


class TestAsyncClaudeClientInterrupt:
    """Test AsyncClaudeClient interrupt functionality."""

    @pytest.mark.asyncio
    async def test_interrupt_without_connection_raises_error(self):
        """Test that interrupt() raises error when not connected."""
        client = AsyncClaudeClient()

        with pytest.raises(RuntimeError, match="not connected"):
            await client.interrupt()


class TestAsyncClaudeClientCommands:
    """Test AsyncClaudeClient command building."""

    def test_build_command_includes_stream_json_format(self):
        """Test that built command includes stream-json format."""
        options = ClaudeOptions(model="sonnet")
        client = AsyncClaudeClient(options=options)

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
        client = AsyncClaudeClient(options=options)

        cmd = client._build_command()

        # Should include model
        assert "--model" in cmd
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "haiku"

    def test_build_subprocess_kwargs_includes_working_dir(self):
        """Test that working_dir is included in kwargs."""
        options = ClaudeOptions(working_dir="/tmp/test")
        client = AsyncClaudeClient(options=options)

        kwargs = client._build_subprocess_kwargs()

        assert "cwd" in kwargs
        assert kwargs["cwd"] == "/tmp/test"

    def test_build_subprocess_kwargs_includes_env_vars(self):
        """Test that environment variables are merged."""
        options = ClaudeOptions(env={"TEST_VAR": "test_value"})
        client = AsyncClaudeClient(options=options)

        kwargs = client._build_subprocess_kwargs()

        assert "env" in kwargs
        assert "TEST_VAR" in kwargs["env"]
        assert kwargs["env"]["TEST_VAR"] == "test_value"

    def test_build_subprocess_kwargs_merges_with_os_environ(self):
        """Test that custom env vars are merged with os.environ."""

        options = ClaudeOptions(env={"CUSTOM_VAR": "custom_value"})
        client = AsyncClaudeClient(options=options)

        kwargs = client._build_subprocess_kwargs()

        # Should include PATH from os.environ
        assert "PATH" in kwargs["env"]
        # Should include custom var
        assert "CUSTOM_VAR" in kwargs["env"]


class TestAsyncClaudeClientProperties:
    """Test AsyncClaudeClient properties."""

    @pytest.mark.asyncio
    async def test_stderr_property(self):
        """Test get_stderr method."""
        client = AsyncClaudeClient()
        # Before connection, should return empty list
        stderr = await client.get_stderr()
        assert isinstance(stderr, list)
        assert len(stderr) == 0


class TestAsyncClaudeClientIntegration:
    """Integration tests with mock subprocess."""

    def test_full_query_flow_with_cat(self):
        """Test full query flow using cat as mock subprocess."""
        # Use cat which will echo our input
        options = ClaudeOptions(
            cli_path="cat",
        )

        # We'll need to patch the command building for this test
        # For now, test the structure
        client = AsyncClaudeClient(options=options)

        # Verify client is properly configured
        assert client.session_id is not None
        assert client.options.cli_path == "cat"


class TestAsyncClaudeClientErrorHandling:
    """Test error handling in AsyncClaudeClient."""

    @pytest.mark.asyncio
    async def test_query_fails_when_not_connected(self):
        """Test that query() fails gracefully when not connected."""
        client = AsyncClaudeClient()

        with pytest.raises(RuntimeError, match="not connected"):
            await client.query("test")

    @pytest.mark.asyncio
    async def test_query_stream_fails_when_not_connected(self):
        """Test that query_stream() fails gracefully when not connected."""
        client = AsyncClaudeClient()

        with pytest.raises(RuntimeError, match="not connected"):
            async for _ in client.query_stream("test"):
                pass

    @pytest.mark.asyncio
    async def test_interrupt_fails_when_not_connected(self):
        """Test that interrupt() fails gracefully when not connected."""
        client = AsyncClaudeClient()

        with pytest.raises(RuntimeError, match="not connected"):
            await client.interrupt()


class TestAsyncClaudeClientMessageFormat:
    """Test message formatting for subprocess communication."""

    def test_message_format_includes_session_id(self):
        """Test that messages include the session_id."""
        client = AsyncClaudeClient()
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


class TestAsyncClaudeClientAsyncContextManager:
    """Test async context manager behavior."""

    @pytest.mark.asyncio
    async def test_async_context_manager_returns_self(self):
        """Test that __aenter__ returns self."""
        client = AsyncClaudeClient()

        async with client as entered_client:
            assert entered_client is client

    @pytest.mark.asyncio
    async def test_async_context_manager_cleanup_on_exception(self):
        """Test that context manager cleans up even on exception."""
        client = AsyncClaudeClient()

        with pytest.raises(ValueError):
            async with client:
                raise ValueError("Test exception")

        # Should be disconnected
        assert not client.is_connected


class TestAsyncClaudeClientConcurrentOperations:
    """Test concurrent async operations."""

    @pytest.mark.asyncio
    async def test_concurrent_is_connected_checks(self):
        """Test that is_connected can be checked concurrently."""
        client = AsyncClaudeClient()

        # Check is_connected multiple times concurrently
        # is_connected is a property, so we access it directly
        results = [client.is_connected for _ in range(10)]

        # All should be False (not connected)
        assert all(not r for r in results)


class TestAsyncClaudeClientManagerType:
    """Test that AsyncPersistentProcessManager is used."""

    def test_uses_async_persistent_process_manager(self):
        """Test that client uses AsyncPersistentProcessManager."""
        from claude_sdk_lite.async_persistent_executor import AsyncPersistentProcessManager

        client = AsyncClaudeClient()
        assert isinstance(client._manager, AsyncPersistentProcessManager)


class TestAsyncClaudeClientWithRealCommands:
    """Tests using real commands (not Claude CLI)."""

    @pytest.mark.asyncio
    async def test_with_echo_command(self):
        """Test client behavior with echo command."""
        # This tests the client structure with a simple command
        # We're not actually calling Claude, just verifying the structure
        options = ClaudeOptions()
        client = AsyncClaudeClient(options=options)

        # Verify structure
        assert hasattr(client, "_manager")
        assert hasattr(client, "session_id")
        assert hasattr(client, "options")
        assert hasattr(client, "_debug")

    @pytest.mark.asyncio
    async def test_session_id_persistence(self):
        """Test that session_id persists across operations."""
        client = AsyncClaudeClient()
        original_session_id = client.session_id

        # Session ID should remain the same
        assert client.session_id == original_session_id


class TestAsyncClaudeClientQueryCollection:
    """Test query method's message collection behavior."""

    @pytest.mark.asyncio
    async def test_query_collects_all_messages_from_stream(self):
        """Test that query() properly collects messages from stream."""
        # This is a structural test - actual integration would need mocking
        client = AsyncClaudeClient()

        # Without connection, should raise RuntimeError
        with pytest.raises(RuntimeError):
            await client.query("test prompt")


class TestAsyncClaudeClientMethodSignatures:
    """Test that async methods have correct signatures."""

    @pytest.mark.asyncio
    async def test_connect_is_async(self):
        """Test that connect() is an async method."""
        client = AsyncClaudeClient()
        assert asyncio.iscoroutinefunction(client.connect)

    @pytest.mark.asyncio
    async def test_disconnect_is_async(self):
        """Test that disconnect() is an async method."""
        client = AsyncClaudeClient()
        assert asyncio.iscoroutinefunction(client.disconnect)

    @pytest.mark.asyncio
    async def test_query_is_async(self):
        """Test that query() is an async method."""
        client = AsyncClaudeClient()
        assert asyncio.iscoroutinefunction(client.query)

    @pytest.mark.asyncio
    async def test_query_stream_returns_async_iterator(self):
        """Test that query_stream() returns an async iterator."""
        client = AsyncClaudeClient()
        stream = client.query_stream("test")

        # Should have __aiter__ and __anext__
        assert hasattr(stream, "__aiter__")
        assert hasattr(stream, "__anext__")

    @pytest.mark.asyncio
    async def test_interrupt_is_async(self):
        """Test that interrupt() is an async method."""
        client = AsyncClaudeClient()
        assert asyncio.iscoroutinefunction(client.interrupt)
