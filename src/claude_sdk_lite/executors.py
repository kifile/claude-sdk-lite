"""Process executors for subprocess management.

This module provides synchronous and asynchronous executors for managing
subprocess interactions with the Claude Code CLI.

Executors are responsible only for:
- Creating subprocess
- Reading raw lines from stdout
- Cleanup

Message parsing is handled in query.py for better separation of concerns.
"""

import asyncio
import subprocess
import sys
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from typing import Any

from claude_sdk_lite.exceptions import ProcessExecutionError


class ProcessExecutor(ABC):
    """Abstract base class for process executors."""

    @abstractmethod
    def execute(
        self,
        cmd: list[str],
        **kwargs: Any,
    ) -> Iterator[bytes]:
        """Execute command and yield raw lines from stdout.

        Args:
            cmd: Command list to execute
            **kwargs: Additional subprocess arguments

        Yields:
            Raw line bytes from stdout
        """


class SyncProcessExecutor(ProcessExecutor):
    """Synchronous subprocess executor using subprocess.Popen."""

    def execute(
        self,
        cmd: list[str],
        **kwargs: Any,
    ) -> Iterator[bytes]:
        """Execute command and yield raw lines from stdout.

        Args:
            cmd: Command list to execute
            **kwargs: Additional subprocess arguments

        Yields:
            Raw line bytes from stdout
        """
        # Prevent console window from appearing on Windows
        if sys.platform == "win32":
            kwargs = kwargs.copy()
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        process = None
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **kwargs,
            )

            if not process.stdout:
                raise RuntimeError("Failed to create subprocess stdout pipe")

            # Read and yield raw lines
            for line in process.stdout:
                yield line

            # Wait for process to complete
            returncode = process.wait()

            if returncode != 0:
                stderr_output = ""
                if process.stderr:
                    stderr_output = process.stderr.read().decode("utf-8", errors="replace")

                raise ProcessExecutionError(
                    message=f"CLI exited with code {returncode}",
                    exit_code=returncode,
                    stderr=stderr_output,
                )

        finally:
            _cleanup_process(process)


def _cleanup_process(process: subprocess.Popen | None) -> None:
    """Clean up a subprocess if it still exists.

    Args:
        process: The subprocess to clean up (may be None)
    """
    if process is None or process.poll() is not None:
        return

    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait()
        except Exception:
            pass


class AsyncProcessExecutor:
    """Asynchronous subprocess executor using asyncio.subprocess."""

    async def async_execute(
        self,
        cmd: list[str],
        **kwargs: Any,
    ) -> AsyncIterator[bytes]:
        """Execute command and yield raw lines from stdout.

        Args:
            cmd: Command list to execute
            **kwargs: Additional subprocess arguments

        Yields:
            Raw line bytes from stdout
        """
        # Prevent console window from appearing on Windows
        if sys.platform == "win32":
            kwargs = kwargs.copy()
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **kwargs,
            )

            if not process.stdout:
                raise RuntimeError("Failed to create subprocess stdout pipe")

            # Read and yield raw lines
            async for line in process.stdout:
                yield line

            # Wait for process to complete
            returncode = await process.wait()

            if returncode != 0:
                stderr_output = ""
                if process.stderr:
                    stderr_output = (await process.stderr.read()).decode("utf-8", errors="replace")

                raise ProcessExecutionError(
                    message=f"CLI exited with code {returncode}",
                    exit_code=returncode,
                    stderr=stderr_output,
                )

        finally:
            await _cleanup_process_async(process)


async def _cleanup_process_async(process: asyncio.subprocess.Process | None) -> None:
    """Clean up an async subprocess if it still exists.

    Args:
        process: The subprocess to clean up (may be None)
    """
    if process is None or process.returncode is not None:
        return

    try:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
