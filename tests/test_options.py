"""Tests for ClaudeOptions command building.

Tests that various options are correctly passed to the claudecode CLI.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_sdk_lite import ClaudeOptions, CLINotFoundError


class TestBasicCommandBuilding:
    """Test basic command building functionality."""

    def test_command_without_prompt(self):
        """Test building command without prompt."""
        options = ClaudeOptions(model="sonnet")
        cmd = options.build_command()
        assert "--model" in cmd
        assert "sonnet" in cmd


class TestModelOptions:
    """Test model-related options."""

    def test_model_option(self):
        """Test --model option."""
        options = ClaudeOptions(model="haiku")
        cmd = options.build_command()
        assert "--model" in cmd
        assert "haiku" in cmd

    def test_fallback_model(self):
        """Test --fallback-model option."""
        options = ClaudeOptions(fallback_model="opus")
        cmd = options.build_command()
        assert "--fallback-model" in cmd
        assert "opus" in cmd

    def test_max_thinking_tokens(self):
        """Test --max-thinking-tokens option."""
        options = ClaudeOptions(max_thinking_tokens=50000)
        cmd = options.build_command()
        assert "--max-thinking-tokens" in cmd
        assert "50000" in cmd


class TestAgentOptions:
    """Test agent-related options."""

    def test_agent_option(self):
        """Test --agent option."""
        options = ClaudeOptions(agent="reviewer")
        cmd = options.build_command()
        assert "--agent" in cmd
        assert "reviewer" in cmd

    def test_agents_json(self):
        """Test --agents option with JSON."""
        agents = {"reviewer": {"description": "Code reviewer", "prompt": "Review the code"}}
        options = ClaudeOptions(agents=agents)
        cmd = options.build_command()
        assert "--agents" in cmd
        # Verify JSON is correctly serialized
        agents_idx = cmd.index("--agents")
        agents_json = json.loads(cmd[agents_idx + 1])
        assert agents_json["reviewer"]["description"] == "Code reviewer"


class TestSystemPromptOptions:
    """Test system prompt options."""

    def test_system_prompt(self):
        """Test --system-prompt option."""
        options = ClaudeOptions(system_prompt="You are a helpful assistant")
        cmd = options.build_command()
        assert "--system-prompt" in cmd
        assert "You are a helpful assistant" in cmd

    def test_append_system_prompt(self):
        """Test --append-system-prompt option."""
        options = ClaudeOptions(append_system_prompt="Always be concise")
        cmd = options.build_command()
        assert "--append-system-prompt" in cmd
        assert "Always be concise" in cmd

    def test_both_system_prompts(self):
        """Test both system prompt options together."""
        options = ClaudeOptions(system_prompt="You are helpful", append_system_prompt="Be concise")
        cmd = options.build_command()
        assert "--system-prompt" in cmd
        assert "--append-system-prompt" in cmd


class TestToolOptions:
    """Test tool-related options."""

    def test_tools_list(self):
        """Test --tools option."""
        options = ClaudeOptions(tools=["Bash", "Edit", "Read"])
        cmd = options.build_command()
        assert "--tools" in cmd
        tools_idx = cmd.index("--tools")
        assert cmd[tools_idx + 1] == "Bash,Edit,Read"

    def test_tools_empty_list(self):
        """Test --tools with empty list (disable all tools)."""
        options = ClaudeOptions(tools=[])
        cmd = options.build_command()
        assert "--tools" in cmd
        tools_idx = cmd.index("--tools")
        assert cmd[tools_idx + 1] == ""

    def test_allowed_tools(self):
        """Test --allowedTools option."""
        options = ClaudeOptions(allowed_tools=["Bash(git:*)", "Edit"])
        cmd = options.build_command()
        assert "--allowedTools" in cmd
        tools_idx = cmd.index("--allowedTools")
        assert cmd[tools_idx + 1] == "Bash(git:*),Edit"

    def test_disallowed_tools(self):
        """Test --disallowedTools option."""
        options = ClaudeOptions(disallowed_tools=["Browser", "Task"])
        cmd = options.build_command()
        assert "--disallowedTools" in cmd


class TestSessionManagementOptions:
    """Test session management options."""

    def test_continue_flag(self):
        """Test --continue flag."""
        options = ClaudeOptions(continue_conversation=True)
        cmd = options.build_command()
        assert "--continue" in cmd

    def test_resume_option(self):
        """Test --resume option."""
        options = ClaudeOptions(resume="session-123")
        cmd = options.build_command()
        assert "--resume" in cmd
        assert "session-123" in cmd

    def test_fork_session_flag(self):
        """Test --fork-session flag."""
        options = ClaudeOptions(fork_session=True)
        cmd = options.build_command()
        assert "--fork-session" in cmd

    def test_session_id(self):
        """Test --session-id option."""
        options = ClaudeOptions(session_id="abc-123-def")
        cmd = options.build_command()
        assert "--session-id" in cmd
        assert "abc-123-def" in cmd

    def test_no_session_persistence(self):
        """Test --no-session-persistence flag."""
        options = ClaudeOptions(no_session_persistence=True)
        cmd = options.build_command()
        assert "--no-session-persistence" in cmd


class TestModeOptions:
    """Test mode-related options."""

    def test_print_mode(self):
        """Test --print flag."""
        options = ClaudeOptions(print_mode=True)
        cmd = options.build_command()
        assert "--print" in cmd

    def test_permission_mode(self):
        """Test --permission-mode option."""
        options = ClaudeOptions(permission_mode="acceptEdits")
        cmd = options.build_command()
        assert "--permission-mode" in cmd
        assert "acceptEdits" in cmd

    def test_permission_mode_invalid(self):
        """Test invalid permission mode raises error."""
        with pytest.raises(ValueError, match="Invalid permission_mode"):
            ClaudeOptions(permission_mode="invalid_mode")

    def test_dangerously_skip_permissions(self):
        """Test --dangerously-skip-permissions flag."""
        options = ClaudeOptions(dangerously_skip_permissions=True)
        cmd = options.build_command()
        assert "--dangerously-skip-permissions" in cmd

    def test_include_partial_messages(self):
        """Test --include-partial-messages flag."""
        options = ClaudeOptions(include_partial_messages=True)
        cmd = options.build_command()
        assert "--include-partial-messages" in cmd


class TestOutputFormatOptions:
    """Test output format options."""

    def test_output_format_json(self):
        """Test --output-format json."""
        options = ClaudeOptions(output_format="json")
        cmd = options.build_command()
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_output_format_stream_json(self):
        """Test --output-format stream-json."""
        options = ClaudeOptions(output_format="stream-json")
        cmd = options.build_command()
        assert "--output-format" in cmd
        assert "stream-json" in cmd

    def test_output_format_invalid(self):
        """Test invalid output format raises error."""
        with pytest.raises(ValueError, match="Invalid output_format"):
            ClaudeOptions(output_format="xml")

    def test_input_format(self):
        """Test --input-format option."""
        options = ClaudeOptions(input_format="stream-json")
        cmd = options.build_command()
        assert "--input-format" in cmd
        assert "stream-json" in cmd

    def test_input_format_invalid(self):
        """Test invalid input format raises error."""
        with pytest.raises(ValueError, match="Invalid input_format"):
            ClaudeOptions(input_format="invalid")


class TestBudgetAndLimitsOptions:
    """Test budget and limit options."""

    def test_max_budget_usd(self):
        """Test --max-budget-usd option."""
        options = ClaudeOptions(max_budget_usd=0.50)
        cmd = options.build_command()
        assert "--max-budget-usd" in cmd
        assert "0.5" in cmd

    def test_max_turns(self):
        """Test --max-turns option."""
        options = ClaudeOptions(max_turns=5)
        cmd = options.build_command()
        assert "--max-turns" in cmd
        assert "5" in cmd


class TestStructuredOutputOptions:
    """Test structured output options."""

    def test_json_schema_dict(self):
        """Test --json-schema with dict."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
        }
        options = ClaudeOptions(json_schema=schema)
        cmd = options.build_command()
        assert "--json-schema" in cmd
        schema_idx = cmd.index("--json-schema")
        schema_json = json.loads(cmd[schema_idx + 1])
        assert schema_json["type"] == "object"
        assert schema_json["properties"]["name"]["type"] == "string"

    def test_json_schema_string(self):
        """Test --json-schema with JSON string."""
        schema_json = '{"type": "object", "properties": {"name": {"type": "string"}}}'
        options = ClaudeOptions(json_schema=schema_json)
        cmd = options.build_command()
        assert "--json-schema" in cmd
        # Check the JSON is in the command (as an element)
        assert any('{"type": "object"' in item for item in cmd)


class TestDirectoryAndFileOptions:
    """Test directory and file options."""

    def test_working_dir_string(self):
        """Test working directory with string."""
        options = ClaudeOptions(working_dir="/path/to/project")
        options.build_command()
        kwargs = options.build_subprocess_kwargs()
        assert kwargs["cwd"] == "/path/to/project"

    def test_working_dir_path(self):
        """Test working directory with Path object."""
        options = ClaudeOptions(working_dir=Path("/path/to/project"))
        kwargs = options.build_subprocess_kwargs()
        assert kwargs["cwd"] == "/path/to/project"

    def test_add_dirs(self):
        """Test --add-dir option."""
        options = ClaudeOptions(add_dirs=["/dir1", "/dir2"])
        cmd = options.build_command()
        add_dir_indices = [i for i, x in enumerate(cmd) if x == "--add-dir"]
        assert len(add_dir_indices) == 2
        assert "/dir1" in cmd
        assert "/dir2" in cmd

    def test_add_dirs_with_path(self):
        """Test --add-dir with Path objects."""
        options = ClaudeOptions(add_dirs=[Path("/dir1"), Path("/dir2")])
        cmd = options.build_command()
        assert "/dir1" in cmd
        assert "/dir2" in cmd


class TestSettingsOptions:
    """Test settings-related options."""

    def test_settings_dict(self):
        """Test --settings with dict."""
        settings = {"key": "value", "enabled": True}
        options = ClaudeOptions(settings=settings)
        cmd = options.build_command()
        assert "--settings" in cmd
        settings_idx = cmd.index("--settings")
        settings_json = json.loads(cmd[settings_idx + 1])
        assert settings_json["key"] == "value"

    def test_settings_string(self):
        """Test --settings with JSON string."""
        settings_json = '{"key": "value"}'
        options = ClaudeOptions(settings=settings_json)
        cmd = options.build_command()
        assert "--settings" in cmd
        assert '{"key": "value"}' in cmd

    def test_setting_sources(self):
        """Test --setting-sources option."""
        options = ClaudeOptions(setting_sources=["user", "project"])
        cmd = options.build_command()
        assert "--setting-sources" in cmd
        assert "user,project" in cmd


class TestMCPOptions:
    """Test MCP server options."""

    def test_mcp_config_dict(self):
        """Test --mcp-config with dict."""
        mcp_config = {"server1": {"command": "node", "args": ["server.js"]}}
        options = ClaudeOptions(mcp_config=mcp_config)
        cmd = options.build_command()
        assert "--mcp-config" in cmd
        mcp_idx = cmd.index("--mcp-config")
        mcp_json = json.loads(cmd[mcp_idx + 1])
        assert "mcpServers" in mcp_json
        assert "server1" in mcp_json["mcpServers"]

    def test_mcp_config_with_mcpServers_key(self):
        """Test --mcp-config when dict already has mcpServers key."""
        mcp_config = {"mcpServers": {"server1": {"command": "node"}}}
        options = ClaudeOptions(mcp_config=mcp_config)
        cmd = options.build_command()
        mcp_idx = cmd.index("--mcp-config")
        mcp_json = json.loads(cmd[mcp_idx + 1])
        assert "server1" in mcp_json["mcpServers"]

    def test_mcp_debug(self):
        """Test --mcp-debug flag."""
        options = ClaudeOptions(mcp_debug=True)
        cmd = options.build_command()
        assert "--mcp-debug" in cmd

    def test_strict_mcp_config(self):
        """Test --strict-mcp-config flag."""
        options = ClaudeOptions(strict_mcp_config=True)
        cmd = options.build_command()
        assert "--strict-mcp-config" in cmd


class TestPluginOptions:
    """Test plugin options."""

    def test_plugin_dir(self):
        """Test --plugin-dir option."""
        options = ClaudeOptions(plugin_dir=["/plugins1", "/plugins2"])
        cmd = options.build_command()
        plugin_indices = [i for i, x in enumerate(cmd) if x == "--plugin-dir"]
        assert len(plugin_indices) == 2

    def test_disable_slash_commands(self):
        """Test --disable-slash-commands flag."""
        options = ClaudeOptions(disable_slash_commands=True)
        cmd = options.build_command()
        assert "--disable-slash-commands" in cmd


class TestBetaOptions:
    """Test beta feature options."""

    def test_betas(self):
        """Test --betas option."""
        options = ClaudeOptions(betas=["feature1", "feature2"])
        cmd = options.build_command()
        assert "--betas" in cmd
        assert "feature1,feature2" in cmd


class TestDebugOptions:
    """Test debug options."""

    def test_debug_flag(self):
        """Test --debug flag."""
        options = ClaudeOptions(debug=True)
        cmd = options.build_command()
        assert "--debug" in cmd

    def test_debug_with_filter(self):
        """Test --debug with filter."""
        options = ClaudeOptions(debug=True, debug_filter="api,hooks")
        cmd = options.build_command()
        assert "--debug" in cmd
        assert "api,hooks" in cmd

    def test_debug_file(self):
        """Test --debug-file option."""
        options = ClaudeOptions(debug_file="/path/to/debug.log")
        cmd = options.build_command()
        assert "--debug-file" in cmd
        assert "/path/to/debug.log" in cmd

    def test_verbose_flag(self):
        """Test --verbose flag."""
        options = ClaudeOptions(verbose=True)
        cmd = options.build_command()
        assert "--verbose" in cmd


class TestIDEIntegrationOptions:
    """Test IDE integration options."""

    def test_ide_flag(self):
        """Test --ide flag."""
        options = ClaudeOptions(ide=True)
        cmd = options.build_command()
        assert "--ide" in cmd

    def test_chrome_flag(self):
        """Test --chrome flag."""
        options = ClaudeOptions(chrome=True)
        cmd = options.build_command()
        assert "--chrome" in cmd

    def test_no_chrome_flag(self):
        """Test --no-chrome flag."""
        options = ClaudeOptions(no_chrome=True)
        cmd = options.build_command()
        assert "--no-chrome" in cmd


class TestFileResourceOptions:
    """Test file resource options."""

    def test_files_option(self):
        """Test --file option."""
        options = ClaudeOptions(files=["file-id-1:relative/path", "file-id-2:other/path"])
        cmd = options.build_command()
        file_indices = [i for i, x in enumerate(cmd) if x == "--file"]
        assert len(file_indices) == 2
        assert "file-id-1:relative/path" in cmd


class TestPROptions:
    """Test PR integration options."""

    def test_from_pr(self):
        """Test --from-pr option."""
        options = ClaudeOptions(from_pr="123")
        cmd = options.build_command()
        assert "--from-pr" in cmd
        assert "123" in cmd

    def test_from_pr_url(self):
        """Test --from-pr option with PR URL."""
        options = ClaudeOptions(from_pr="https://github.com/user/repo/pull/42")
        cmd = options.build_command()
        assert "--from-pr" in cmd
        assert "https://github.com/user/repo/pull/42" in cmd

    def test_from_pr_search_term(self):
        """Test --from-pr option with search term."""
        options = ClaudeOptions(from_pr="fix auth bug")
        cmd = options.build_command()
        assert "--from-pr" in cmd
        assert "fix auth bug" in cmd


class TestEnvironmentOptions:
    """Test environment variables."""

    def test_env_variables(self):
        """Test passing environment variables."""
        options = ClaudeOptions(env={"API_KEY": "test-key", "DEBUG": "true"})
        kwargs = options.build_subprocess_kwargs()
        assert "env" in kwargs
        assert kwargs["env"]["API_KEY"] == "test-key"
        assert kwargs["env"]["DEBUG"] == "true"

    def test_env_merges_with_os_environ(self, monkeypatch):
        """Test that custom env is merged with OS environment."""
        monkeypatch.setenv("EXISTING_VAR", "existing_value")
        options = ClaudeOptions(env={"NEW_VAR": "new_value"})
        kwargs = options.build_subprocess_kwargs()
        assert kwargs["env"]["EXISTING_VAR"] == "existing_value"
        assert kwargs["env"]["NEW_VAR"] == "new_value"


class TestExtraArgsOptions:
    """Test extra arguments for forward compatibility."""

    def test_extra_args_with_values(self):
        """Test extra_args with values."""
        options = ClaudeOptions(extra_args={"new-flag": "value", "another-flag": "another-value"})
        cmd = options.build_command()
        assert "--new-flag" in cmd
        assert "value" in cmd
        assert "--another-flag" in cmd
        assert "another-value" in cmd

    def test_extra_args_boolean_flags(self):
        """Test extra_args with boolean flags (None value)."""
        options = ClaudeOptions(extra_args={"new-bool-flag": None, "another-bool": None})
        cmd = options.build_command()
        assert "--new-bool-flag" in cmd
        assert "--another-bool" in cmd
        # Check the flags appear in order (boolean flags don't have values after them)
        new_bool_idx = cmd.index("--new-bool-flag")
        another_bool_idx = cmd.index("--another-bool")
        # For two consecutive boolean flags, one immediately follows the other
        assert another_bool_idx == new_bool_idx + 1


class TestComplexScenarios:
    """Test complex realistic scenarios."""

    def test_full_options_ci_cd_scenario(self):
        """Test a typical CI/CD scenario with many options."""
        options = ClaudeOptions(
            model="haiku",
            print_mode=True,
            output_format="stream-json",
            max_budget_usd=0.10,
            max_turns=1,
            system_prompt="You are a code reviewer",
            permission_mode="acceptEdits",
            disallowed_tools=["Browser", "Task"],
            working_dir="/path/to/repo",
        )
        cmd = options.build_command("Review the code")
        kwargs = options.build_subprocess_kwargs()

        # Verify all options are present
        assert "--model" in cmd
        assert "haiku" in cmd
        assert "--print" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--max-budget-usd" in cmd
        assert "--max-turns" in cmd
        assert "--system-prompt" in cmd
        assert "--permission-mode" in cmd
        assert "--disallowedTools" in cmd
        assert "Review the code" in cmd
        assert kwargs["cwd"] == "/path/to/repo"

    def test_development_scenario_with_mcp(self):
        """Test a development scenario with MCP servers."""
        options = ClaudeOptions(
            model="sonnet",
            agent="coder",
            mcp_config={
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
                }
            },
            allowed_tools=["Bash(*)", "Edit", "Read"],
            debug=True,
        )
        cmd = options.build_command()

        assert "--agent" in cmd
        assert "--mcp-config" in cmd
        assert "--allowedTools" in cmd
        assert "--debug" in cmd


class TestCLIPathValidation:
    """Test CLI path validation in _find_cli_path."""

    def test_custom_cli_path_executable(self):
        """Test command with custom CLI path that exists and is executable."""
        # Use a known executable for testing
        options = ClaudeOptions(cli_path="/bin/ls")
        cmd = options.build_command("test")
        assert cmd[0] == "/bin/ls"

    def test_non_executable_cli_path(self):
        """Test error when specified cli_path is not executable."""
        # Create a temporary file that is not executable
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".sh") as f:
            temp_path = f.name
            f.write("#!/bin/bash\necho test\n")

        try:
            # Make sure it's not executable
            os.chmod(temp_path, 0o644)

            options = ClaudeOptions(cli_path=temp_path)

            # On Unix, this should fail if the file is not executable
            # On Windows, os.access check might behave differently
            if os.name != "nt":  # Skip on Windows
                with pytest.raises(CLINotFoundError, match="not executable"):
                    options.build_command("test")
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_cli_path_not_found(self):
        """Test error when specified cli_path does not exist."""
        options = ClaudeOptions(cli_path="/nonexistent/path/to/claude")
        with pytest.raises(CLINotFoundError, match="does not exist"):
            options.build_command("test")

    def test_working_dir_in_kwargs(self):
        """Test that working_dir is passed to subprocess kwargs."""
        # Mock find_tool to avoid actual CLI search
        with patch("claude_sdk_lite.utils.find_tool_in_system_sync", return_value="/bin/ls"):
            options = ClaudeOptions(working_dir="/custom/path")
            options.build_command("test")
            kwargs = options.build_subprocess_kwargs()
            assert kwargs["cwd"] == "/custom/path"

    def test_env_vars_merged(self):
        """Test that custom env vars are merged with os.environ."""
        # Mock find_tool to avoid actual CLI search
        with patch("claude_sdk_lite.utils.find_tool_in_system_sync", return_value="/bin/ls"):
            options = ClaudeOptions(env={"CUSTOM_VAR": "custom_value"})
            kwargs = options.build_subprocess_kwargs()
            assert "env" in kwargs
            assert kwargs["env"]["CUSTOM_VAR"] == "custom_value"
            # Should also contain existing environment variables
            assert "PATH" in kwargs["env"]
