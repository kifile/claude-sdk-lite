"""Claude Code CLI options for lightweight subprocess invocation.

This module provides a simplified options interface for calling the Claude Code CLI
via subprocess, designed for projects that already have claudecode installed.
Based on the official claude-agent-sdk-python ClaudeAgentOptions design.
"""

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from claude_sdk_lite.exceptions import CLINotFoundError


class ClaudeOptions(BaseModel):
    """Lightweight options for invoking Claude Code CLI via subprocess.

    This class maps to Claude Code CLI arguments, providing a Python interface
    for subprocess calls without the overhead of the full SDK.

    Example:
        ```python
        options = ClaudeOptions(
            model="sonnet",
            print_mode=True,
            system_prompt="You are a helpful assistant",
        )
        cmd = options.build_command("Hello, Claude!")
        subprocess.run(cmd)
        ```
    """

    # ===== Core Options =====

    model: str | None = Field(
        default=None, description="Model to use (e.g., 'sonnet', 'opus', 'haiku')"
    )
    agent: str | None = Field(default=None, description="Agent name for the current session")
    agents: dict[str, dict[str, Any]] | None = Field(
        default=None,
        description="Custom agent definitions as JSON object",
        examples=[
            {"reviewer": {"description": "Reviews code", "prompt": "You are a code reviewer"}}
        ],
    )

    # ===== System Prompt =====

    system_prompt: str | None = Field(
        default=None, description="System prompt to use for the session"
    )
    append_system_prompt: str | None = Field(
        default=None, description="Append a system prompt to the default system prompt"
    )

    # ===== Tools =====

    tools: list[str] | None = Field(
        default=None,
        description="List of available tools from built-in set. Use empty list to disable all tools.",
    )
    allowed_tools: list[str] = Field(
        default_factory=list,
        description="Comma-separated list of tool names to allow (e.g., ['Bash(git:*)', 'Edit'])",
    )
    disallowed_tools: list[str] = Field(
        default_factory=list,
        description="Comma-separated list of tool names to deny",
    )

    # ===== Session Management =====

    continue_conversation: bool = Field(
        default=False,
        description="Continue the most recent conversation in the current directory",
        alias="continue",
    )
    resume: str | None = Field(
        default=None, description="Resume a conversation by session ID, or search term"
    )
    fork_session: bool = Field(
        default=False,
        description="When resuming, create a new session ID instead of reusing the original",
    )
    session_id: str | None = Field(
        default=None,
        description="Use a specific session ID for the conversation (must be a valid UUID)",
    )
    no_session_persistence: bool = Field(
        default=False,
        description="Disable session persistence - sessions will not be saved to disk",
    )

    # ===== Mode Options =====

    print_mode: bool = Field(
        default=False,
        description="Print response and exit (non-interactive mode, useful for pipes)",
        alias="print",
    )
    replay_user_messages: bool = Field(
        default=False,
        description="Replay user input through message stream (enables --replay-user-messages flag)",
    )
    permission_mode: str | None = Field(
        default=None,
        description="Permission mode: 'default', 'acceptEdits', 'plan', 'bypassPermissions', 'delegate', 'dontAsk'",
    )
    dangerously_skip_permissions: bool = Field(
        default=False,
        description="Bypass all permission checks (recommended only for sandboxes)",
    )

    # ===== Output Format =====

    output_format: str = Field(
        default="text",
        description="Output format: 'text' (default), 'json', or 'stream-json'",
    )
    input_format: str = Field(
        default="text",
        description="Input format: 'text' (default) or 'stream-json'",
    )
    include_partial_messages: bool = Field(
        default=False,
        description="Include partial message chunks as they arrive (only with --print and --output-format=stream-json)",
    )

    # ===== Budget and Limits =====

    max_budget_usd: float | None = Field(
        default=None,
        description="Maximum dollar amount to spend on API calls (only works with --print)",
    )
    max_turns: int | None = Field(
        default=None,
        description="Maximum number of turns to execute",
    )

    # ===== Model Options =====

    fallback_model: str | None = Field(
        default=None,
        description="Enable automatic fallback to specified model when default model is overloaded",
    )
    max_thinking_tokens: int | None = Field(
        default=None,
        description="Max tokens for thinking blocks",
    )

    # ===== Structured Output =====

    json_schema: dict[str, Any] | str | None = Field(
        default=None,
        description="JSON Schema for structured output validation (dict or JSON string)",
        examples=[{"type": "object", "properties": {"name": {"type": "string"}}}],
    )

    # ===== Directories and Files =====

    working_dir: str | Path | None = Field(
        default=None,
        description="Working directory for the CLI execution",
    )
    add_dirs: list[str | Path] = Field(
        default_factory=list,
        description="Additional directories to allow tool access to",
    )

    # ===== Settings =====

    settings: str | dict[str, Any] | None = Field(
        default=None,
        description="Path to settings JSON file, or JSON string, or settings dict",
    )
    setting_sources: list[str] = Field(
        default_factory=list,
        description="Setting sources to load: 'user', 'project', 'local'",
    )

    # ===== MCP Servers =====

    mcp_config: str | dict[str, Any] | None = Field(
        default=None,
        description="Load MCP servers from JSON files or strings (file path, JSON string, or dict)",
    )
    mcp_debug: bool = Field(
        default=False,
        description="Enable MCP debug mode (shows MCP server errors)",
    )
    strict_mcp_config: bool = Field(
        default=False,
        description="Only use MCP servers from --mcp-config, ignoring all other MCP configurations",
    )

    # ===== Plugins =====

    plugin_dir: list[str | Path] = Field(
        default_factory=list,
        description="Load plugins from directories for this session only",
    )
    disable_slash_commands: bool = Field(
        default=False,
        description="Disable all skills (slash commands)",
    )

    # ===== Beta Features =====

    betas: list[str] = Field(
        default_factory=list,
        description="Beta headers to include in API requests (API key users only)",
    )

    # ===== Debug =====

    debug: bool = Field(default=False, description="Enable debug mode")
    debug_filter: str | None = Field(
        default=None,
        description="Debug filter for specific categories (e.g., 'api,hooks' or '!1p,!file')",
    )
    debug_file: str | None = Field(
        default=None,
        description="Write debug logs to a specific file path (implicitly enables debug mode)",
    )
    verbose: bool = Field(
        default=False,
        description="Override verbose mode setting from config",
    )

    # ===== IDE Integration =====

    ide: bool = Field(
        default=False,
        description="Automatically connect to IDE on startup if exactly one valid IDE is available",
    )
    chrome: bool = Field(
        default=False,
        description="Enable Claude in Chrome integration",
    )
    no_chrome: bool = Field(
        default=False,
        description="Disable Claude in Chrome integration",
    )

    # ===== File Resources =====

    files: list[str] = Field(
        default_factory=list,
        description="File resources to download at startup. Format: file_id:relative_path",
    )

    # ===== PR Integration =====

    from_pr: str | None = Field(
        default=None,
        description="Resume a session linked to a PR by PR number/URL, or search term",
    )

    # ===== Additional Options =====

    cli_path: str | Path | None = Field(
        default=None,
        description="Path to the Claude Code CLI binary (if not in PATH)",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Additional environment variables for the subprocess",
    )
    extra_args: dict[str, str | None] = Field(
        default_factory=dict,
        description="Pass arbitrary CLI flags not covered by this class",
        examples=[{"some-flag": "value", "boolean-flag": None}],
    )

    model_config = ConfigDict(
        populate_by_name=True,  # Allow using aliases (continue, print)
        arbitrary_types_allowed=True,  # Allow Path types
    )

    @field_validator("permission_mode")
    def validate_permission_mode(cls, v: str | None) -> str | None:
        """Validate permission mode value."""
        if v is None:
            return v
        valid_modes = {
            "default",
            "acceptEdits",
            "plan",
            "bypassPermissions",
            "delegate",
            "dontAsk",
        }
        if v not in valid_modes:
            raise ValueError(
                f"Invalid permission_mode: {v}. Must be one of: {', '.join(valid_modes)}"
            )
        return v

    @field_validator("output_format")
    def validate_output_format(cls, v: str) -> str:
        """Validate output format value."""
        valid_formats = {"text", "json", "stream-json"}
        if v not in valid_formats:
            raise ValueError(
                f"Invalid output_format: {v}. Must be one of: {', '.join(valid_formats)}"
            )
        return v

    @field_validator("input_format")
    def validate_input_format(cls, v: str) -> str:
        """Validate input format value."""
        valid_formats = {"text", "stream-json"}
        if v not in valid_formats:
            raise ValueError(
                f"Invalid input_format: {v}. Must be one of: {', '.join(valid_formats)}"
            )
        return v

    def _find_cli_path(self) -> str:
        """Find the Claude Code CLI executable path.

        Returns:
            The path to the claude CLI executable.

        Raises:
            CLINotFoundError: If the CLI cannot be found.
        """
        # Import here to avoid circular imports
        from claude_sdk_lite.utils import find_tool_in_system_sync

        # If cli_path is explicitly specified, use it
        if self.cli_path:
            cli_path = Path(self.cli_path)
            # Check if the specified path exists
            if not cli_path.exists():
                raise CLINotFoundError(
                    f"Specified Claude Code CLI path does not exist: {cli_path}\n"
                    f"Please check the path or install Claude Code CLI:\n"
                    f"  npm install -g @anthropic-ai/claude-code"
                )
            # Check if it's executable
            if not os.access(cli_path, os.X_OK):
                raise CLINotFoundError(
                    f"Specified path is not executable: {cli_path}\n"
                    f"Please make sure the file has execute permissions."
                )
            return str(cli_path)

        # Try to find claude in PATH using our utility function
        cli_path = find_tool_in_system_sync("claude")
        if cli_path:
            return cli_path

        # CLI not found
        raise CLINotFoundError(
            "Claude Code CLI not found in PATH.\n"
            "Please install it with:\n"
            "  npm install -g @anthropic-ai/claude-code\n"
            "Or specify the path via: ClaudeOptions(cli_path='/path/to/claude')"
        )

    def build_command(self, prompt: str | None = None) -> list[str]:
        """Build the complete command list for subprocess invocation.

        Args:
            prompt: Optional prompt to include as an argument.

        Returns:
            List of command arguments suitable for subprocess.run() or similar.

        Raises:
            CLINotFoundError: If the Claude Code CLI cannot be found.

        Example:
            ```python
            options = ClaudeOptions(print_mode=True)
            cmd = options.build_command("Hello!")
            # ['claude', '--print', 'Hello!']
            subprocess.run(cmd, capture_output=True)
            ```
        """
        # Find and validate CLI path
        cli_path = self._find_cli_path()

        # Start with base command
        cmd = [cli_path]

        # Output format (for JSON/streaming modes)
        if self.output_format != "text":
            cmd.extend(["--output-format", self.output_format])

        # Input format
        if self.input_format != "text":
            cmd.extend(["--input-format", self.input_format])

        # Model
        if self.model:
            cmd.extend(["--model", self.model])

        # Agent
        if self.agent:
            cmd.extend(["--agent", self.agent])

        # Agents (JSON)
        if self.agents:
            cmd.extend(["--agents", json.dumps(self.agents)])

        # System prompt
        if self.system_prompt is not None:
            cmd.extend(["--system-prompt", self.system_prompt])

        # Append system prompt
        if self.append_system_prompt:
            cmd.extend(["--append-system-prompt", self.append_system_prompt])

        # Tools
        if self.tools is not None:
            if len(self.tools) == 0:
                cmd.extend(["--tools", ""])
            else:
                cmd.extend(["--tools", ",".join(self.tools)])

        # Allowed tools
        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])

        # Disallowed tools
        if self.disallowed_tools:
            cmd.extend(["--disallowedTools", ",".join(self.disallowed_tools)])

        # Session management
        if self.continue_conversation:
            cmd.append("--continue")

        if self.resume:
            cmd.extend(["--resume", self.resume])

        if self.fork_session:
            cmd.append("--fork-session")

        if self.session_id:
            cmd.extend(["--session-id", self.session_id])

        if self.no_session_persistence:
            cmd.append("--no-session-persistence")

        # Mode options
        if self.print_mode:
            cmd.append("--print")

        if self.replay_user_messages:
            cmd.append("--replay-user-messages")

        if self.permission_mode:
            cmd.extend(["--permission-mode", self.permission_mode])

        if self.dangerously_skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        # Partial messages
        if self.include_partial_messages:
            cmd.append("--include-partial-messages")

        # Budget and limits
        if self.max_budget_usd is not None:
            cmd.extend(["--max-budget-usd", str(self.max_budget_usd)])

        if self.max_turns is not None:
            cmd.extend(["--max-turns", str(self.max_turns)])

        # Model options
        if self.fallback_model:
            cmd.extend(["--fallback-model", self.fallback_model])

        if self.max_thinking_tokens is not None:
            cmd.extend(["--max-thinking-tokens", str(self.max_thinking_tokens)])

        # JSON schema
        if self.json_schema:
            if isinstance(self.json_schema, dict):
                schema_json = json.dumps(self.json_schema)
            else:
                schema_json = self.json_schema
            cmd.extend(["--json-schema", schema_json])

        # Add directories
        if self.add_dirs:
            for directory in self.add_dirs:
                cmd.extend(["--add-dir", str(directory)])

        # Settings
        if self.settings:
            if isinstance(self.settings, dict):
                settings_json = json.dumps(self.settings)
            elif isinstance(self.settings, Path):
                settings_json = str(self.settings)
            else:
                settings_json = self.settings
            cmd.extend(["--settings", settings_json])

        # Setting sources
        if self.setting_sources:
            cmd.extend(["--setting-sources", ",".join(self.setting_sources)])

        # MCP config
        if self.mcp_config:
            if isinstance(self.mcp_config, dict):
                # Process all servers, stripping instance field from SDK servers
                servers_for_cli: dict[str, Any] = {}
                if "mcpServers" in self.mcp_config:
                    # Has mcpServers key, process each server
                    for name, config in self.mcp_config["mcpServers"].items():
                        if isinstance(config, dict) and config.get("type") == "sdk":
                            # For SDK servers, pass everything except the instance field
                            sdk_config: dict[str, object] = {
                                k: v for k, v in config.items() if k != "instance"
                            }
                            servers_for_cli[name] = sdk_config
                        else:
                            # For external servers, pass as-is
                            servers_for_cli[name] = config
                    mcp_config = {"mcpServers": servers_for_cli}
                else:
                    # No mcpServers key, treat entire dict as servers
                    for name, config in self.mcp_config.items():
                        if isinstance(config, dict) and config.get("type") == "sdk":
                            sdk_config: dict[str, object] = {
                                k: v for k, v in config.items() if k != "instance"
                            }
                            servers_for_cli[name] = sdk_config
                        else:
                            servers_for_cli[name] = config
                    mcp_config = {"mcpServers": servers_for_cli}
                mcp_json = json.dumps(mcp_config)
            elif isinstance(self.mcp_config, Path):
                mcp_json = str(self.mcp_config)
            else:
                mcp_json = self.mcp_config
            cmd.extend(["--mcp-config", mcp_json])

        if self.mcp_debug:
            cmd.append("--mcp-debug")

        if self.strict_mcp_config:
            cmd.append("--strict-mcp-config")

        # Plugins
        if self.plugin_dir:
            for plugin_path in self.plugin_dir:
                cmd.extend(["--plugin-dir", str(plugin_path)])

        if self.disable_slash_commands:
            cmd.append("--disable-slash-commands")

        # Beta features
        if self.betas:
            cmd.extend(["--betas", ",".join(self.betas)])

        # Debug options
        if self.debug:
            if self.debug_filter:
                cmd.extend(["--debug", self.debug_filter])
            else:
                cmd.append("--debug")

        if self.debug_file:
            cmd.extend(["--debug-file", self.debug_file])

        if self.verbose:
            cmd.append("--verbose")

        # IDE integration
        if self.ide:
            cmd.append("--ide")

        if self.chrome:
            cmd.append("--chrome")

        if self.no_chrome:
            cmd.append("--no-chrome")

        # File resources
        if self.files:
            for file_spec in self.files:
                cmd.extend(["--file", file_spec])

        # PR integration
        if self.from_pr:
            cmd.extend(["--from-pr", self.from_pr])

        # Extra args (arbitrary flags)
        for flag, value in self.extra_args.items():
            if value is None:
                # Boolean flag without value
                cmd.append(f"--{flag}")
            else:
                # Flag with value
                cmd.extend([f"--{flag}", str(value)])

        # Add prompt if provided
        if prompt:
            cmd.append(prompt)

        return cmd

    def build_subprocess_kwargs(self) -> dict[str, Any]:
        """Build subprocess keyword arguments.

        Returns:
            Dictionary of kwargs suitable for subprocess.run():
            - cwd: Working directory
            - env: Environment variables (merged with os.environ)

        Example:
            ```python
            options = ClaudeOptions(working_dir="/path/to/project")
            kwargs = options.build_subprocess_kwargs()
            subprocess.run(options.build_command(), **kwargs)
            ```
        """
        import os

        result: dict[str, Any] = {}

        # Working directory
        if self.working_dir:
            result["cwd"] = str(self.working_dir)

        # Environment variables
        if self.env:
            # Merge with current environment
            result["env"] = {**os.environ, **self.env}

        return result
