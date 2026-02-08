"""Exception classes for claude-sdk-lite."""


class ClaudeSDKLiteError(Exception):
    """Base exception for all claude-sdk-lite errors."""


class QueryError(ClaudeSDKLiteError):
    """Base error for query failures."""


class CLINotFoundError(QueryError):
    """Claude Code CLI not found."""


class CLIExecutionError(QueryError):
    """CLI execution failed with non-zero exit code."""

    def __init__(self, message: str, exit_code: int | None = None, stderr: str | None = None):
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(message)


class ProcessExecutionError(RuntimeError):
    """Error raised when subprocess execution fails.

    This exception is used internally by executors to communicate
    execution failures to the query layer.
    """

    def __init__(self, message: str, exit_code: int, stderr: str):
        self.message = message
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(message)
