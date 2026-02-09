"""Async persistent subprocess executor for long-running sessions.

This module provides an async executor for maintaining persistent subprocess
connections with bidirectional communication, designed for session-based interactions
with the Claude Code CLI.

The executor manages:
- Long-running subprocess with stdin/stdout communication
- Async tasks for reading/writing
- Stderr capture for debugging
- Interrupt capabilities
- Thread-safe operations with proper locking
- Error propagation from worker tasks
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from claude_sdk_lite.exceptions import ProcessExecutionError

logger = logging.getLogger(__name__)

# Maximum number of stderr lines to keep in buffer
MAX_STDERR_LINES = 100

# Maximum queue size to prevent unbounded memory growth
MAX_QUEUE_SIZE = 1000

# Default timeouts (in seconds)
DEFAULT_READ_TIMEOUT = 30.0
TASK_WAIT_TIMEOUT = 1.0
PROCESS_WAIT_TIMEOUT = 5.0
DRAIN_QUEUE_MAX_ITEMS = 1000

# Initialization wait timeout
MAX_INITIALIZATION_WAIT_TIME = 5.0


class AsyncPersistentProcessManager:
    """Async manager for persistent subprocess connections.

    This class handles long-running subprocess connections with bidirectional
    communication via stdin/stdout, designed specifically for session-based
    interactions where multiple queries are sent over the same connection.

    Example:
        ```python
        manager = AsyncPersistentProcessManager()
        try:
            # Start persistent process
            await manager.start(cmd, **kwargs)

            # Send request
            await manager.write_request({"type": "user_message", ...})

            # Read response
            async for line in manager.read_lines():
                await process_line(line)

            # Send interrupt if needed
            await manager.write_interrupt()

        finally:
            await manager.stop()
        ```
    """

    def __init__(self) -> None:
        """Initialize the async persistent process manager."""
        # State lock for thread-safe lifecycle management
        self._lock = asyncio.Lock()
        self._process: asyncio.subprocess.Process | None = None
        self._stdin_queue: asyncio.Queue[dict[str, Any] | None] | None = None
        self._stdin_task: asyncio.Task[None] | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._line_queue: asyncio.Queue[bytes | None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._stderr_buffer: list[str] = []
        self._stderr_lock: asyncio.Lock | None = None

        # Error queue for propagating exceptions from worker tasks
        self._error_queue: asyncio.Queue[Exception] | None = None

        # Condition variable for initialization synchronization
        # Allows stop() to efficiently wait for start() to complete
        self._init_cond = asyncio.Condition(self._lock)

        # Initialization flag to prevent race conditions during start()
        self._initializing = False

        # Cache debug flag to avoid repeated environment variable lookups
        self._debug = os.environ.get("CLAUDE_SDK_DEBUG", "false").lower() == "true"

    async def start(
        self,
        cmd: list[str],
        **kwargs: Any,
    ) -> None:
        """Start persistent subprocess for session-based interaction.

        Thread-safe method that initializes the subprocess and communication
        structures. Uses internal lock to prevent race conditions.

        Args:
            cmd: Command list to execute
            **kwargs: Additional subprocess arguments

        Raises:
            RuntimeError: If process is already running
            FileNotFoundError: If command executable not found
        """
        async with self._lock:
            if self._process is not None:
                raise RuntimeError("Process already running")

            # Set initialization flag to prevent stop() from interfering
            self._initializing = True

            try:
                # Start process with stdin for bidirectional communication
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **kwargs,
                )

                if (
                    self._process.stdin is None
                    or self._process.stdout is None
                    or self._process.stderr is None
                ):
                    await self._cleanup()
                    raise RuntimeError("Failed to create subprocess pipes")

                # Initialize communication structures with bounded queues
                self._stdin_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
                self._line_queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
                self._stop_event = asyncio.Event()
                self._stderr_buffer = []
                self._stderr_lock = asyncio.Lock()

                # Initialize error queue
                self._error_queue = asyncio.Queue()

                # Create all tasks
                self._stdin_task = asyncio.create_task(
                    self._stdin_writer(),
                    name="async-persistent-stdin-writer",
                )
                self._stdout_task = asyncio.create_task(
                    self._stdout_reader(),
                    name="async-persistent-stdout-reader",
                )
                self._stderr_task = asyncio.create_task(
                    self._stderr_reader(),
                    name="async-persistent-stderr-reader",
                )

            finally:
                # Clear initialization flag and notify waiting tasks
                self._initializing = False
                self._init_cond.notify_all()

    async def stop(self) -> None:
        """Stop persistent subprocess and cleanup resources.

        Thread-safe method that ensures proper cleanup order:
        1. Wait for initialization if in progress
        2. Signal tasks to stop
        3. Terminate process (causes EOF in pipes)
        4. Wait for tasks to finish
        5. Clear all references

        This method is safe to call multiple times.
        """
        async with self._init_cond:
            # Wait for initialization to complete if in progress
            wait_start = asyncio.get_event_loop().time()
            while self._initializing:
                remaining = MAX_INITIALIZATION_WAIT_TIME - (
                    asyncio.get_event_loop().time() - wait_start
                )
                if remaining <= 0:
                    logger.warning(
                        "Initialization still in progress after %.1fs, proceeding with stop",
                        MAX_INITIALIZATION_WAIT_TIME,
                    )
                    break
                try:
                    await asyncio.wait_for(self._init_cond.wait(), timeout=min(0.1, remaining))
                except asyncio.TimeoutError:
                    break

            if self._process is None:
                return

            # Signal tasks to stop
            if self._stop_event:
                self._stop_event.set()

            # Signal stdin writer to stop
            if self._stdin_queue:
                try:
                    self._stdin_queue.put_nowait(None)
                except asyncio.QueueFull:
                    self._log_debug("Failed to send shutdown signal to stdin writer (queue full)")

            # Cleanup process FIRST
            await self._cleanup()

            # Wait for tasks to finish
            if self._stdin_task and not self._stdin_task.done():
                try:
                    await asyncio.wait_for(self._stdin_task, timeout=TASK_WAIT_TIMEOUT)
                except asyncio.TimeoutError:
                    self._stdin_task.cancel()
                    try:
                        await self._stdin_task
                    except asyncio.CancelledError:
                        pass

            if self._stdout_task and not self._stdout_task.done():
                try:
                    await asyncio.wait_for(self._stdout_task, timeout=TASK_WAIT_TIMEOUT)
                except asyncio.TimeoutError:
                    self._stdout_task.cancel()
                    try:
                        await self._stdout_task
                    except asyncio.CancelledError:
                        pass

            if self._stderr_task and not self._stderr_task.done():
                try:
                    await asyncio.wait_for(self._stderr_task, timeout=TASK_WAIT_TIMEOUT)
                except asyncio.TimeoutError:
                    self._stderr_task.cancel()
                    try:
                        await self._stderr_task
                    except asyncio.CancelledError:
                        pass

            # Clear references
            self._process = None
            self._stdin_queue = None
            self._line_queue = None
            self._stop_event = None
            self._error_queue = None
            self._stdin_task = None
            self._stdout_task = None
            self._stderr_task = None
            self._stderr_buffer = []
            self._stderr_lock = None

    async def write_request(self, request: dict[str, Any]) -> None:
        """Write a request to subprocess stdin.

        This method is thread-safe and uses reference capture to prevent
        race conditions with stop().

        Args:
            request: Dictionary to send as JSON

        Raises:
            RuntimeError: If process not running
        """
        async with self._lock:
            if self._stdin_queue is None:
                raise RuntimeError("Process not running. Call start() first.")
            # Capture queue reference
            queue = self._stdin_queue

        # Put outside lock
        await queue.put(request)

    async def read_lines(self, timeout: float = DEFAULT_READ_TIMEOUT) -> AsyncIterator[bytes]:
        """Read lines from stdout.

        Args:
            timeout: Seconds to wait for each line (default: 30.0)

        Yields:
            Raw line bytes from stdout

        Raises:
            RuntimeError: If process not running
            ProcessExecutionError: If process terminates unexpectedly
        """
        async with self._lock:
            if self._line_queue is None or self._process is None:
                raise RuntimeError("Process not running. Call start() first.")
            line_queue = self._line_queue
            process = self._process

        self._log_debug("Starting to read lines (timeout=%s)", timeout)

        try:
            iteration_count = 0
            while True:
                iteration_count += 1
                try:
                    self._log_debug("Waiting for line... (iteration #%d)", iteration_count)

                    line = await asyncio.wait_for(line_queue.get(), timeout=timeout)
                    if line is None:  # Sentinel for EOF
                        self._log_debug("Received EOF sentinel")
                        break

                    self._log_debug("Got line: %d bytes", len(line))
                    yield line

                except asyncio.TimeoutError:
                    # Timeout - check if process is still alive
                    self._log_debug("Timeout after %ss, checking process...", timeout)

                    # Check for worker task errors
                    if task_error := await self.check_error():
                        raise RuntimeError(f"Worker task error: {task_error}") from task_error

                    if process.returncode is not None:
                        # Process died
                        self._log_debug("Process is dead! exit code: %s", process.returncode)

                        stderr_output = await self._get_stderr_copy()
                        if stderr_output:
                            self._log_debug("Stderr output:\n%s", stderr_output)

                        raise ProcessExecutionError(
                            f"Process terminated unexpectedly (exit code {process.returncode})",
                            exit_code=process.returncode or -1,
                            stderr=stderr_output,
                        )
                    # Continue waiting if process is still running
                    self._log_debug("Process still alive, continuing to wait...")
                    continue

        except GeneratorExit:
            # Generator was closed before completion
            self._log_debug("Generator closed by caller, draining line queue")
            await self._drain_line_queue()
            raise

        self._log_debug("read_lines() completed after %d iterations", iteration_count)

    async def write_interrupt(self) -> None:
        """Send interrupt signal via stdin."""
        # Generate unique request ID using secrets for cryptographic security
        import secrets

        request_id = f"req_{secrets.token_hex(8)}"

        control_request = {
            "type": "control_request",
            "request_id": request_id,
            "subtype": "interrupt",
        }

        await self.write_request(control_request)

    async def get_stderr(self) -> list[str]:
        """Get captured stderr output.

        Returns:
            List of stderr lines
        """
        if self._stderr_lock is None:
            return list(self._stderr_buffer) if self._stderr_buffer else []

        async with self._stderr_lock:
            return list(self._stderr_buffer) if self._stderr_buffer else []

    async def _get_stderr_copy(self) -> str:
        """Get thread-safe copy of stderr buffer as a string.

        Returns:
            Stderr output as a string
        """
        if self._stderr_lock is None:
            return "\n".join(self._stderr_buffer) if self._stderr_buffer else ""

        async with self._stderr_lock:
            return "\n".join(self._stderr_buffer) if self._stderr_buffer else ""

    async def _drain_line_queue(self) -> None:
        """Drain all remaining items from the line queue.

        This is called when a generator is closed prematurely to prevent
        memory leaks and ensure clean state for subsequent calls.
        """
        if self._line_queue is None:
            return

        drained = 0
        while drained < DRAIN_QUEUE_MAX_ITEMS:
            try:
                item = self._line_queue.get_nowait()
                if item is None:
                    # EOF sentinel - put it back
                    try:
                        self._line_queue.put_nowait(None)
                    except asyncio.QueueFull:
                        pass
                    break
                # Discard any other items
                drained += 1
            except asyncio.QueueEmpty:
                break

        if drained >= DRAIN_QUEUE_MAX_ITEMS:
            self._log_debug("Drained line queue hit max limit (%d items)", DRAIN_QUEUE_MAX_ITEMS)

    def is_alive(self) -> bool:
        """Check if the process is still running.

        This method is thread-safe and uses internal locking to ensure
        consistent state when checking process status.

        Returns:
            True if process is running, False otherwise
        """
        # Note: This is a synchronous check
        return self._process is not None and self._process.returncode is None

    async def check_error(self) -> Exception | None:
        """Check for errors from worker tasks.

        This method should be called periodically to detect if any
        worker tasks have encountered exceptions.

        Returns:
            The first exception from the error queue, or None if no errors
        """
        if self._error_queue is None:
            return None

        try:
            return self._error_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def _capture_exception(self, e: Exception) -> None:
        """Capture an exception from a worker task.

        Args:
            e: The exception to capture
        """
        if self._error_queue is not None:
            await self._error_queue.put(e)

    def _log_debug(self, message: str, *args: Any) -> None:
        """Log debug message only if debug mode is enabled.

        Args:
            message: The log message format string
            *args: Arguments for string formatting
        """
        if self._debug:
            logger.debug(message, *args)

    # ========== Private Methods ==========

    async def _stdin_writer(self) -> None:
        """Background task that writes requests to stdin."""
        if self._process is None or self._process.stdin is None:
            return

        try:
            while not (self._stop_event and self._stop_event.is_set()):
                try:
                    request = await self._stdin_queue.get()  # type: ignore
                    if request is None:  # Sentinel for shutdown
                        break

                    # Check stop flag after getting request
                    if self._stop_event and self._stop_event.is_set():
                        break

                    # Write JSON line to stdin
                    line = json.dumps(request) + "\n"
                    self._process.stdin.write(line.encode())
                    await self._process.stdin.drain()

                except (BrokenPipeError, ConnectionError) as e:
                    # Pipe broken - capture and exit
                    await self._capture_exception(e)
                    break

        except Exception as e:
            # Capture unexpected exceptions
            await self._capture_exception(e)
            self._log_debug("Error in stdin writer: %s", e)

    async def _stdout_reader(self) -> None:
        """Background task that reads lines from stdout."""
        if self._process is None or self._process.stdout is None:
            return

        self._log_debug("[STDOUT] Reader task started")

        try:
            line_count = 0
            while not (self._stop_event and self._stop_event.is_set()):
                try:
                    line = await self._process.stdout.readline()
                    if not line:  # EOF
                        self._log_debug("[STDOUT] EOF received (read %d lines total)", line_count)
                        break

                    line_count += 1
                    self._log_debug("[STDOUT] Read line #%d: %d bytes", line_count, len(line))

                    if self._line_queue:
                        # Put line in queue with backpressure
                        try:
                            await asyncio.wait_for(
                                self._line_queue.put(line),
                                timeout=1.0,
                            )
                        except asyncio.TimeoutError:
                            self._log_debug("[STDOUT] Queue full, dropping line #%d", line_count)

                except Exception as e:
                    self._log_debug("[STDOUT] Exception: %s", e)
                    await self._capture_exception(e)
                    break

        except Exception as e:
            self._log_debug("[STDOUT] Task exception: %s", e)
            await self._capture_exception(e)
        finally:
            # Signal EOF
            self._log_debug("[STDOUT] Signaling EOF")
            if self._line_queue:
                try:
                    self._line_queue.put_nowait(None)
                except asyncio.QueueFull:
                    self._log_debug("[STDOUT] Failed to send EOF sentinel (queue full)")

    async def _stderr_reader(self) -> None:
        """Background task that reads stderr output."""
        if self._process is None or self._process.stderr is None:
            return

        try:
            while not (self._stop_event and self._stop_event.is_set()):
                try:
                    line = await self._process.stderr.readline()
                    if not line:  # EOF
                        break

                    line_str = line.decode().strip()
                    if line_str:
                        # Use lock to protect concurrent access
                        if self._stderr_lock:
                            async with self._stderr_lock:
                                self._stderr_buffer.append(line_str)
                                # Keep buffer manageable
                                if len(self._stderr_buffer) > MAX_STDERR_LINES:
                                    self._stderr_buffer = self._stderr_buffer[-MAX_STDERR_LINES:]

                except Exception as e:
                    await self._capture_exception(e)
                    break

        except Exception as e:
            await self._capture_exception(e)
            self._log_debug("Error in stderr reader: %s", e)

    async def _cleanup(self) -> None:
        """Clean up the subprocess if it still exists."""
        if self._process is None or self._process.returncode is not None:
            return

        try:
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=PROCESS_WAIT_TIMEOUT)
        except asyncio.TimeoutExpired:
            try:
                self._process.kill()
                await self._process.wait()
            except Exception as e:
                self._log_debug("Error killing subprocess: %s", e)
        except Exception as e:
            self._log_debug("Error terminating subprocess: %s", e)

    async def __aenter__(self) -> "AsyncPersistentProcessManager":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        _ = exc_type, exc_val, exc_tb  # Unused
        await self.stop()
