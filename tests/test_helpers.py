"""Shared test fixtures and utilities for cross-platform compatibility."""

import platform
import sys

import pytest

# ========== Platform Detection ==========
IS_WINDOWS = platform.system() == "Windows"
is_windows = IS_WINDOWS  # Alias for consistency


# ========== Cross-Platform Command Helpers ==========

def get_cat_command():
    """Get a command that reads from stdin and writes to stdout."""
    if IS_WINDOWS:
        # PowerShell script that reads stdin and writes to stdout
        return [
            "powershell",
            "-NoProfile",
            "-Command",
            "$input | ForEach-Object { Write-Output $_ }",
        ]
    return ["cat"]


def get_true_command():
    """Get a command that exits successfully with no output."""
    if IS_WINDOWS:
        return ["cmd.exe", "/c", "exit 0"]
    return ["true"]


def get_false_command():
    """Get a command that exits with code 1."""
    if IS_WINDOWS:
        return ["cmd.exe", "/c", "exit 1"]
    return ["false"]


def get_head_command(lines=1):
    """Get a command that reads N lines from stdin then exits."""
    import sys
    # Use Python script for cross-platform compatibility
    return [
        sys.executable,
        "-u",
        "-c",
        f"import sys; [print(sys.stdin.readline(), end='') for _ in range({lines})]",
    ]


def get_grep_command(pattern):
    """Get a command that filters input by pattern."""
    if IS_WINDOWS:
        # PowerShell to filter by pattern
        return [
            "powershell",
            "-NoProfile",
            "-Command",
            f"$input | Where-Object {{ $_ -match '{pattern}' }}",
        ]
    return ["grep", pattern]


def get_echo_command(text):
    """Get a command that outputs text."""
    import sys
    # Use Python script for cross-platform compatibility
    return [sys.executable, "-u", "-c", f"print('{text}')"]


def get_echo_command_args():
    """Get a command that outputs arguments (for testing echo with args)."""
    import sys
    # Use Python script that prints all arguments
    return [sys.executable, "-u", "-c", "import sys; print(' '.join(sys.argv[1:]))"]


def get_sleep_command(seconds):
    """Get a command that sleeps for N seconds."""
    if IS_WINDOWS:
        return ["timeout", "/t", str(int(seconds * 10)), "/nobreak"]
    return ["sleep", str(seconds)]


def get_seq_command(start, end=None):
    """Get a command that outputs a sequence of numbers."""
    if end is None:
        end = start
        start = 1

    if IS_WINDOWS:
        # PowerShell to generate sequence
        return [
            "powershell",
            "-NoProfile",
            "-Command",
            f"{start}..{end} | ForEach-Object {{ Write-Output $_ }}",
        ]
    return ["seq", str(start), str(end)]


def get_shell_command():
    """Get appropriate shell command for the platform."""
    if IS_WINDOWS:
        return ["cmd.exe", "/c"]
    return ["sh", "-c"]


def create_json_command(json_lines):
    """Create a command that outputs JSON lines, one per line.

    Args:
        json_lines: List of JSON strings to output

    Returns:
        Command list for subprocess
    """
    if IS_WINDOWS:
        # PowerShell to output JSON lines
        escaped_lines = [line.replace('"', '`"') for line in json_lines]
        lines_script = "; ".join(f'Write-Output "{line}"' for line in escaped_lines)
        return ["powershell", "-NoProfile", "-Command", lines_script]
    else:
        # Use printf for consistent output
        lines_str = "\\n".join(json_lines)
        return ["sh", "-c", f"printf '{lines_str}\\n'"]


def create_echo_script(commands):
    """Create a shell command that runs multiple echo commands.

    Args:
        commands: List of shell command strings to execute

    Returns:
        Command list for subprocess
    """
    if IS_WINDOWS:
        # Join commands with & for Windows
        combined = " & ".join(commands)
        return ["cmd.exe", "/c", combined]
    else:
        # Join commands with && for Unix
        combined = " && ".join(commands)
        return ["sh", "-c", combined]


def create_stderr_command(message, stdout_message="{}"):
    """Create a command that writes to stderr and optionally to stdout.

    Args:
        message: Message to write to stderr
        stdout_message: Optional JSON message to write to stdout

    Returns:
        Command list for subprocess
    """
    if IS_WINDOWS:
        stderr_cmd = f"echo {message} >&2"
        if stdout_message:
            return ["cmd.exe", "/c", f'{stderr_cmd} & echo "{stdout_message}"']
        return ["cmd.exe", "/c", stderr_cmd]
    else:
        stderr_cmd = f"echo '{message}' >&2"
        if stdout_message:
            return ["sh", "-c", f'{stderr_cmd} && echo "{stdout_message}"']
        return ["sh", "-c", stderr_cmd]


def create_error_command(exit_code, stderr_message=""):
    """Create a command that exits with custom error code.

    Args:
        exit_code: Exit code to return
        stderr_message: Optional message to write to stderr

    Returns:
        Command list for subprocess
    """
    if IS_WINDOWS:
        if stderr_message:
            return ["cmd.exe", "/c", f"echo {stderr_message} >&2 & exit {exit_code}"]
        return ["cmd.exe", "/c", f"exit {exit_code}"]
    else:
        if stderr_message:
            return ["sh", "-c", f"echo '{stderr_message}' >&2; exit {exit_code}"]
        return ["sh", "-c", f"exit {exit_code}"]


def create_loop_script(num_iterations, output_template):
    """Create a command that loops and outputs template messages.

    Args:
        num_iterations: Number of loop iterations
        output_template: String template with {i} placeholder for iteration

    Returns:
        Command list for subprocess
    """
    if IS_WINDOWS:
        # PowerShell for loop
        script = f"1..{num_iterations} | ForEach-Object {{ " + f"{output_template}" + " }}"
        return ["powershell", "-NoProfile", "-Command", script]
    else:
        # Shell for loop
        script = f"for i in $(seq 1 {num_iterations}); do {output_template}; done"
        return ["sh", "-c", script]


def create_python_script(script_content):
    """Create a command that runs a Python script.

    Args:
        script_content: Python code to run

    Returns:
        Command list for subprocess
    """
    return [sys.executable, "-u", "-c", script_content]


def skip_if_windows_unless(condition=True):
    """Skip test on Windows unless condition is met.

    Args:
        condition: If True, test runs on all platforms. If False, skipped on Windows.
    """
    return pytest.mark.skipif(
        IS_WINDOWS and not condition,
        reason="Test not compatible with Windows"
    )


# ========== Pytest fixtures ==========

@pytest.fixture
def is_windows():
    """Fixture that returns True if running on Windows."""
    return IS_WINDOWS


@pytest.fixture
def cat_command():
    """Fixture that returns platform-appropriate cat command."""
    return get_cat_command()


@pytest.fixture
def true_command():
    """Fixture that returns platform-appropriate true command."""
    return get_true_command()
