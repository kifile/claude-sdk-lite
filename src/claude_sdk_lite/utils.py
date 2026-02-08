"""Utility functions for claude-sdk-lite."""

import platform

from claude_sdk_lite.executors import AsyncProcessExecutor, SyncProcessExecutor


def _get_command_for_system(tool_name: str) -> list[str]:
    """Get the appropriate command for finding tools on the current system.

    Args:
        tool_name: Tool name to search for

    Returns:
        Command list for 'where' (Windows) or 'which' (Unix)
    """
    system = platform.system().lower()

    if system == "windows":
        return ["where", tool_name]
    else:
        return ["which", tool_name]


def _select_best_path(output_lines: list[str], system: str) -> str | None:
    """Select the best path from 'where' or 'which' output.

    Args:
        output_lines: List of paths from the command output
        system: Lowercase system name (e.g., 'windows', 'darwin', 'linux')

    Returns:
        The best path, or None if no paths found
    """
    # Remove trailing empty line if any
    if output_lines and output_lines[-1] == "":
        output_lines.pop()

    if not output_lines:
        return None

    # On Windows, prefer .exe over .cmd/.bat extensions
    if system == "windows":
        # First, try to find .exe (most preferred)
        for path in output_lines:
            if path.lower().endswith(".exe"):
                return path

        # Then, try to find .cmd or .bat
        for path in output_lines:
            if any(path.lower().endswith(ext) for ext in [".cmd", ".bat"]):
                return path

        # If no extension found, return first path (might be Unix-style script)
        return output_lines[0]
    else:
        # Unix-like systems return first path directly
        return output_lines[0]


async def find_tool_in_system(tool_name: str) -> str | None:
    """
    Find tool path in system (async version).

    Args:
        tool_name: Tool name

    Returns:
        Tool path or None
    """
    system = platform.system().lower()
    command = _get_command_for_system(tool_name)

    try:
        executor = AsyncProcessExecutor()

        # Collect all output lines
        output_lines = []
        async for line in executor.async_execute(command):
            output_lines.append(line.decode().strip())

        return _select_best_path(output_lines, system)

    except (OSError, RuntimeError):
        return None


def find_tool_in_system_sync(tool_name: str) -> str | None:
    """
    Find tool path in system (sync version).

    Args:
        tool_name: Tool name

    Returns:
        Tool path or None
    """
    system = platform.system().lower()
    command = _get_command_for_system(tool_name)

    try:
        executor = SyncProcessExecutor()

        # Collect all output lines
        output_lines = []
        for line in executor.execute(command):
            output_lines.append(line.decode().strip())

        return _select_best_path(output_lines, system)

    except (OSError, RuntimeError):
        return None
