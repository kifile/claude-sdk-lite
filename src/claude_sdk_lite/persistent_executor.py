"""Persistent subprocess executor for long-running sessions.

This module provides a specialized executor for maintaining persistent subprocess
connections with bidirectional communication, designed for session-based interactions
with the Claude Code CLI.

The executor manages:
- Long-running subprocess with stdin/stdout communication
- Background threads for reading/writing
- Stderr capture for debugging
- Interrupt capabilities
- Thread-safe operations with proper locking
- Error propagation from worker threads
"""

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from queue import Queue, SimpleQueue
from typing import Any

from claude_sdk_lite.exceptions import ProcessExecutionError

logger = logging.getLogger(__name__)

# Maximum number of stderr lines to keep in buffer
MAX_STDERR_LINES = 100

# Maximum queue size to prevent unbounded memory growth
MAX_QUEUE_SIZE = 1000

# Default timeouts (in seconds)
DEFAULT_READ_TIMEOUT = 30.0
THREAD_JOIN_TIMEOUT = 0.5
PROCESS_WAIT_TIMEOUT = 5.0
DRAIN_QUEUE_MAX_ITEMS = 1000
QUEUE_PUT_TIMEOUT = 1.0

# Initialization wait timeout
MAX_INITIALIZATION_WAIT_TIME = 5.0


class PersistentProcessManager:
    """Manager for persistent subprocess connections.

    This class handles long-running subprocess connections with bidirectional
    communication via stdin/stdout, designed specifically for session-based
    interactions where multiple queries are sent over the same connection.

    Example:
        ```python
        manager = PersistentProcessManager()
        try:
            # Start persistent process
            manager.start(cmd, **kwargs)

            # Send request
            manager.write_request({"type": "user_message", ...})

            # Read response
            for line in manager.read_lines():
                process_line(line)

            # Send interrupt if needed
            manager.write_interrupt()

        finally:
            manager.stop()
        ```
    """

    def __init__(self) -> None:
        """Initialize the persistent process manager."""
        # State lock for thread-safe lifecycle management
        self._state_lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._stdin_queue: Queue[dict[str, Any] | None] | None = None
        self._stdin_thread: threading.Thread | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._line_queue: Queue[bytes | None] | None = None
        self._stop_event: threading.Event | None = None
        self._stderr_buffer: list[str] = []
        self._stderr_lock: threading.Lock | None = None

        # Error queue for propagating exceptions from worker threads
        self._error_queue: SimpleQueue[Exception] | None = None

        # Condition variable for initialization synchronization
        # Allows stop() to efficiently wait for start() to complete
        self._init_cond = threading.Condition(self._state_lock)

        # Initialization flag to prevent race conditions during start()
        self._initializing = False

        # Cache debug flag to avoid repeated environment variable lookups
        self._debug = os.environ.get("CLAUDE_SDK_DEBUG", "false").lower() == "true"

    def start(
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
        with self._state_lock:
            if self._process is not None:
                raise RuntimeError("Process already running")

            # Set initialization flag to prevent stop() from interfering
            self._initializing = True

            try:
                # Prevent console window on Windows and create new process group
                if sys.platform == "win32":
                    kwargs = kwargs.copy()
                    kwargs["creationflags"] = (
                        subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                    )
                else:
                    # Unix/Linux: start_new_session puts the subprocess in a new session
                    # This prevents Ctrl+C from being forwarded to the subprocess
                    kwargs = kwargs.copy()
                    kwargs["start_new_session"] = True

                # Start process with stdin for bidirectional communication
                # Use bufsize=0 for unbuffered I/O (critical for pipe communication)
                self._process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,  # Unbuffered
                    **kwargs,
                )

                if not self._process.stdin or not self._process.stdout or not self._process.stderr:
                    self._cleanup()
                    raise RuntimeError("Failed to create subprocess pipes")

                # Initialize communication structures with bounded queues to prevent
                # unbounded memory growth. Use Queue instead of SimpleQueue for size limits.
                self._stdin_queue = Queue(maxsize=MAX_QUEUE_SIZE)
                self._line_queue = Queue(maxsize=MAX_QUEUE_SIZE)
                self._stop_event = threading.Event()
                self._stderr_buffer = []
                self._stderr_lock = threading.Lock()

                # Initialize error queue for thread error propagation
                # Keep SimpleQueue for errors as they should be rare
                self._error_queue = SimpleQueue()

                # Create all threads first
                self._stdin_thread = threading.Thread(
                    target=self._stdin_writer,
                    name="persistent-stdin-writer",
                    daemon=True,
                )
                self._stdout_thread = threading.Thread(
                    target=self._stdout_reader,
                    name="persistent-stdout-reader",
                    daemon=True,
                )
                self._stderr_thread = threading.Thread(
                    target=self._stderr_reader,
                    name="persistent-stderr-reader",
                    daemon=True,
                )

                # Start all threads
                self._stdin_thread.start()
                self._stdout_thread.start()
                self._stderr_thread.start()

            finally:
                # Clear initialization flag and notify waiting threads
                self._initializing = False
                self._init_cond.notify_all()

    def stop(self) -> None:
        """Stop persistent subprocess and cleanup resources.

        Thread-safe method that ensures proper cleanup order:
        1. Wait for initialization if in progress
        2. Signal threads to stop
        3. Terminate process (causes EOF in pipes)
        4. Wait for threads to finish
        5. Clear all references

        This method is safe to call multiple times.
        """
        with self._init_cond:
            # Wait for initialization to complete if in progress
            # This prevents race conditions where stop() is called during start()
            wait_start = time.time()
            while self._initializing:
                remaining = MAX_INITIALIZATION_WAIT_TIME - (time.time() - wait_start)
                if remaining <= 0:
                    logger.warning(
                        "Initialization still in progress after %.1fs, proceeding with stop",
                        MAX_INITIALIZATION_WAIT_TIME,
                    )
                    break
                # Wait with timeout to avoid deadlock
                self._init_cond.wait(timeout=min(0.1, remaining))

            if self._process is None:
                return

            # Signal threads to stop
            if self._stop_event:
                self._stop_event.set()

            # Signal stdin writer to stop
            # Note: Queue is unbounded for put operations, so this won't block
            if self._stdin_queue:
                try:
                    self._stdin_queue.put(None, block=False)
                except queue.Full:
                    # Queue is full, try with timeout
                    try:
                        self._stdin_queue.put(None, timeout=QUEUE_PUT_TIMEOUT)
                    except queue.Full:
                        self._log_debug(
                            "Failed to send shutdown signal to stdin writer (queue full)"
                        )

            # Cleanup process FIRST - this causes readline() to return EOF,
            # allowing reader threads to exit quickly
            self._cleanup()

            # Wait for threads to finish (should be fast now that process is terminated)
            if self._stdin_thread and self._stdin_thread.is_alive():
                self._stdin_thread.join(timeout=THREAD_JOIN_TIMEOUT)

            if self._stdout_thread and self._stdout_thread.is_alive():
                self._stdout_thread.join(timeout=THREAD_JOIN_TIMEOUT)

            if self._stderr_thread and self._stderr_thread.is_alive():
                self._stderr_thread.join(timeout=THREAD_JOIN_TIMEOUT)

            # Clear references
            self._process = None
            self._stdin_queue = None
            self._line_queue = None
            self._stop_event = None
            self._error_queue = None
            self._stdin_thread = None
            self._stdout_thread = None
            self._stderr_thread = None
            self._stderr_buffer = []
            self._stderr_lock = None

    def write_request(self, request: dict[str, Any]) -> None:
        """Write a request to subprocess stdin.

        This method is thread-safe and uses reference capture to prevent
        race conditions with stop().

        Args:
            request: Dictionary to send as JSON

        Raises:
            RuntimeError: If process not running
        """
        with self._state_lock:
            if self._stdin_queue is None:
                raise RuntimeError("Process not running. Call start() first.")
            # Capture queue reference to prevent race with stop()
            # This ensures we use the same queue object even if stop() is called
            queue = self._stdin_queue

        # Put outside lock to avoid holding it during potentially blocking operation
        queue.put(request)

    def read_lines(self, timeout: float = DEFAULT_READ_TIMEOUT) -> Iterator[bytes]:
        """Read lines from stdout.

        Args:
            timeout: Seconds to wait for each line (default: 30.0)

        Yields:
            Raw line bytes from stdout

        Raises:
            RuntimeError: If process not running
            ProcessExecutionError: If process terminates unexpectedly
        """
        if self._line_queue is None or self._process is None:
            raise RuntimeError("Process not running. Call start() first.")

        self._log_debug("Starting to read lines (timeout=%s)", timeout)

        try:
            iteration_count = 0
            while True:
                iteration_count += 1
                try:
                    self._log_debug("Waiting for line... (iteration #%d)", iteration_count)

                    line = self._line_queue.get(timeout=timeout)
                    if line is None:  # Sentinel for EOF
                        self._log_debug("Received EOF sentinel")
                        break

                    self._log_debug("Got line: %d bytes", len(line))
                    yield line

                except queue.Empty:
                    # Timeout - check if process is still alive
                    self._log_debug("Timeout after %ss, checking process...", timeout)

                    # Check for worker thread errors
                    if thread_error := self.check_error():
                        raise RuntimeError(f"Worker thread error: {thread_error}") from thread_error

                    if self._process.poll() is not None:
                        # Process died
                        self._log_debug("Process is dead! exit code: %s", self._process.returncode)

                        stderr_output = self._get_stderr_copy()
                        if stderr_output:
                            self._log_debug("Stderr output:\n%s", stderr_output)

                        raise ProcessExecutionError(
                            f"Process terminated unexpectedly (exit code {self._process.returncode})",
                            exit_code=self._process.returncode or -1,
                            stderr=stderr_output,
                        )
                    # Continue waiting if process is still running
                    self._log_debug("Process still alive, continuing to wait...")
                    continue

        except GeneratorExit:
            # Generator was closed before completion
            # Clean up any pending data in the queue to prevent memory leaks
            self._log_debug("Generator closed by caller, draining line queue")
            self._drain_line_queue()
            raise

        self._log_debug("read_lines() completed after %d iterations", iteration_count)

    def write_interrupt(self) -> None:
        """Send interrupt signal via stdin."""
        # Generate unique request ID using secrets for cryptographic security
        import secrets

        request_id = f"req_{secrets.token_hex(8)}"

        control_request = {
            "type": "control_request",
            "request_id": request_id,
            "subtype": "interrupt",
        }

        self.write_request(control_request)

    def get_stderr(self) -> list[str]:
        """Get captured stderr output.

        Returns:
            List of stderr lines
        """
        if self._stderr_lock is None:
            # Fallback if lock is not initialized (shouldn't happen in normal use)
            return list(self._stderr_buffer) if self._stderr_buffer else []

        with self._stderr_lock:
            return list(self._stderr_buffer) if self._stderr_buffer else []

    def _get_stderr_copy(self) -> str:
        """Get thread-safe copy of stderr buffer as a string.

        Returns:
            Stderr output as a string
        """
        if self._stderr_lock is None:
            # Fallback if lock is not initialized (shouldn't happen in normal use)
            return "\n".join(self._stderr_buffer) if self._stderr_buffer else ""

        with self._stderr_lock:
            return "\n".join(self._stderr_buffer) if self._stderr_buffer else ""

    def _drain_line_queue(self) -> None:
        """Drain all remaining items from the line queue.

        This is called when a generator is closed prematurely to prevent
        memory leaks and ensure clean state for subsequent calls.

        Uses non-blocking get with a maximum item limit to avoid
        infinite loops or excessive processing time.
        """
        if self._line_queue is None:
            return

        drained = 0
        while drained < DRAIN_QUEUE_MAX_ITEMS:
            try:
                item = self._line_queue.get_nowait()
                if item is None:
                    # EOF sentinel - put it back for potential future readers
                    try:
                        self._line_queue.put(None, block=False)
                    except queue.Full:
                        # Queue is full, sentinel already exists, that's fine
                        pass
                    break
                # Discard any other items
                drained += 1
            except queue.Empty:
                # Queue is empty, we're done
                break

        if drained >= DRAIN_QUEUE_MAX_ITEMS:
            # Log if we hit the limit - might indicate a problem
            self._log_debug("Drained line queue hit max limit (%d items)", DRAIN_QUEUE_MAX_ITEMS)

    def is_alive(self) -> bool:
        """Check if the process is still running.

        This method is thread-safe and uses internal locking to ensure
        consistent state when checking process status.

        Returns:
            True if process is running, False otherwise
        """
        with self._state_lock:
            return self._process is not None and self._process.poll() is None

    def check_error(self) -> Exception | None:
        """Check for errors from worker threads.

        This method should be called periodically to detect if any
        worker threads have encountered exceptions.

        Returns:
            The first exception from the error queue, or None if no errors
        """
        if self._error_queue is None:
            return None

        try:
            return self._error_queue.get_nowait()
        except queue.Empty:
            return None

    def _capture_exception(self, e: Exception) -> None:
        """Capture an exception from a worker thread.

        Args:
            e: The exception to capture
        """
        if self._error_queue is not None:
            self._error_queue.put(e)

    def _log_debug(self, message: str, *args: Any) -> None:
        """Log debug message only if debug mode is enabled.

        This avoids the overhead of string formatting when debug is off.

        Args:
            message: The log message format string
            *args: Arguments for string formatting
        """
        if self._debug:
            logger.debug(message, *args)

    # ========== Private Methods ==========

    def _stdin_writer(self) -> None:
        """Background thread that writes requests to stdin."""
        if not self._process or not self._process.stdin:
            return

        try:
            while not (self._stop_event and self._stop_event.is_set()):
                try:
                    # Block indefinitely waiting for requests
                    # The sentinel (None) will be sent by stop() to signal shutdown
                    request = self._stdin_queue.get()
                    if request is None:  # Sentinel for shutdown
                        break

                    # Check stop flag after getting request
                    if self._stop_event and self._stop_event.is_set():
                        break

                    # Write JSON line to stdin
                    line = json.dumps(request) + "\n"
                    self._process.stdin.write(line.encode())
                    self._process.stdin.flush()

                except (OSError, BrokenPipeError) as e:
                    # Pipe broken - capture and exit
                    self._capture_exception(e)
                    break

        except Exception as e:
            # Capture unexpected exceptions
            self._capture_exception(e)
            self._log_debug("Error in stdin writer: %s", e)

    def _stdout_reader(self) -> None:
        """Background thread that reads lines from stdout."""
        if not self._process or not self._process.stdout:
            return

        self._log_debug("[STDOUT] Reader thread started")

        try:
            line_count = 0
            while not (self._stop_event and self._stop_event.is_set()):
                try:
                    line = self._process.stdout.readline()
                    if not line:  # EOF
                        self._log_debug("[STDOUT] EOF received (read %d lines total)", line_count)
                        break

                    line_count += 1
                    self._log_debug("[STDOUT] Read line #%d: %d bytes", line_count, len(line))

                    if self._line_queue:
                        # Put line in queue with backpressure
                        # If queue is full, block to prevent unbounded memory growth
                        try:
                            self._line_queue.put(line, block=True, timeout=QUEUE_PUT_TIMEOUT)
                        except queue.Full:
                            # Queue is full and we've waited too long
                            # This indicates the consumer is not keeping up
                            self._log_debug("[STDOUT] Queue full, dropping line #%d", line_count)
                            # Continue reading to avoid blocking the subprocess

                except Exception as e:
                    self._log_debug("[STDOUT] Exception: %s", e)
                    self._capture_exception(e)
                    break

        except Exception as e:
            self._log_debug("[STDOUT] Thread exception: %s", e)
            self._capture_exception(e)
        finally:
            # Signal EOF
            self._log_debug("[STDOUT] Signaling EOF")
            if self._line_queue:
                try:
                    self._line_queue.put(None, block=False)
                except queue.Full:
                    # Queue is full, try with timeout
                    try:
                        self._line_queue.put(None, timeout=QUEUE_PUT_TIMEOUT)
                    except queue.Full:
                        self._log_debug("[STDOUT] Failed to send EOF sentinel (queue full)")

    def _stderr_reader(self) -> None:
        """Background thread that reads stderr output."""
        if not self._process or not self._process.stderr:
            return

        try:
            while not (self._stop_event and self._stop_event.is_set()):
                try:
                    line = self._process.stderr.readline()
                    if not line:  # EOF
                        break

                    line_str = line.decode().strip()
                    if line_str:
                        # Use lock to protect concurrent access to stderr_buffer
                        if self._stderr_lock:
                            with self._stderr_lock:
                                self._stderr_buffer.append(line_str)
                                # Keep buffer manageable (last MAX_STDERR_LINES lines)
                                if len(self._stderr_buffer) > MAX_STDERR_LINES:
                                    self._stderr_buffer = self._stderr_buffer[-MAX_STDERR_LINES:]

                except Exception as e:
                    self._capture_exception(e)
                    break

        except Exception as e:
            self._capture_exception(e)
            self._log_debug("Error in stderr reader: %s", e)

    def _cleanup(self) -> None:
        """Clean up the subprocess if it still exists."""
        if self._process is None or self._process.poll() is not None:
            return

        try:
            self._process.terminate()
            self._process.wait(timeout=PROCESS_WAIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            try:
                self._process.kill()
                self._process.wait()
            except Exception as e:
                self._log_debug("Error killing subprocess: %s", e)
        except Exception as e:
            self._log_debug("Error terminating subprocess: %s", e)

    def __enter__(self) -> "PersistentProcessManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        _ = exc_type, exc_val, exc_tb  # Unused
        self.stop()
