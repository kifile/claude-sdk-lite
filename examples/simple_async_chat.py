#!/usr/bin/env python3
"""Async interactive chat example using AsyncClaudeClient with custom handler.

This demonstrates a minimal async chatbot with:
- Multi-turn conversation
- Context retention
- Double Ctrl+C to exit (single Ctrl+C interrupts)
- Clean exit handling
- Event-driven message handling via custom MessageEventListener
"""

import asyncio
import logging
import os
import time

# Configure logging to show debug messages when CLAUDE_SDK_DEBUG is enabled
logging.basicConfig(level=logging.DEBUG, format="%(name)s - %(levelname)s - %(message)s")

from claude_sdk_lite import (
    AssistantMessage,
    AsyncClaudeClient,
    AsyncMessageEventListener,
    ClaudeOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

# Time window for double Ctrl+C to trigger exit
DOUBLE_INTERRUPT_TIMEOUT = 2.0

# Enable debug mode to see all messages
DEBUG = os.environ.get("CLAUDE_SDK_DEBUG", "false").lower() == "true"


class AsyncChatMessageHandler(AsyncMessageEventListener):
    """Custom async message handler for chat interface.

    This handler buffers messages and provides async callbacks for the chat UI.
    """

    def __init__(self):
        """Initialize the async chat handler."""
        self.messages = []
        self.complete_event = None

    async def on_query_start(self, prompt: str):
        """Called when a query starts."""
        if DEBUG:
            print(f"\n[DEBUG] Query started: {prompt[:50]}...", flush=True)
        self.messages = []
        self.complete_event = asyncio.Event()

    async def on_message(self, message):
        """Called when any message is received."""
        self.messages.append(message)

        # Print assistant messages in real-time
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"\nClaude: {block.text}", end="", flush=True)
                elif isinstance(block, ToolUseBlock):
                    print(f"\n[Tool: {block.name}] {block.input}", end="", flush=True)
                elif isinstance(block, ThinkingBlock):
                    print(f"\n[Thinking...]", end="", flush=True)
                else:
                    print(f"\n[{type(block)}]")
        elif isinstance(message, SystemMessage):
            print(f"\n[System: {message.data.get('subtype', 'unknown')}]", end="", flush=True)
        elif isinstance(message, ResultMessage):
            print("\nResult: ", end="", flush=True)
            if message.is_error:
                print(f"\n[Error: {message.result}]", end="", flush=True)
            else:
                # Show cost if available
                if message.total_cost_usd:
                    print(
                        f"\n\n[Cost: ${message.total_cost_usd:.4f} | Turns: {message.num_turns}]",
                        end="",
                        flush=True,
                    )
                elif message.num_turns:
                    print(f"\n\n[Turns: {message.num_turns}]", end="", flush=True)

    async def on_query_complete(self, messages):
        """Called when a query completes."""
        if DEBUG:
            print(f"\n[DEBUG] Query complete: {len(messages)} messages", flush=True)

        if self.complete_event:
            self.complete_event.set()

    async def on_error(self, error):
        """Called when an error occurs."""
        print(f"\n[Error: {error}]", flush=True)


class SimpleAsyncChat:
    """Async interactive chat interface with improved UX."""

    def __init__(self, options: ClaudeOptions):
        """Initialize the async chat interface.

        Args:
            options: Configuration options for the session.
        """
        self.options = options
        self.handler = AsyncChatMessageHandler()
        self.client = AsyncClaudeClient(options=options, message_handler=self.handler)
        self.last_interrupt_time = None
        self.is_thinking = False

    async def handle_interrupt(self):
        """Handle Ctrl+C with double-interrupt detection.

        This is an async method that may call client.interrupt().

        Returns:
            bool: True if session should continue (single-interrupt),
                  False if session should exit (double-interrupt)
        """
        current_time = time.time()

        # Check if this is a double-interrupt
        if self.last_interrupt_time is not None:
            time_since_last = current_time - self.last_interrupt_time

            if time_since_last < DOUBLE_INTERRUPT_TIMEOUT:
                # Double interrupt detected - exit
                print("\n\n[Double interrupt detected. Exiting...]")
                return False  # Signal to exit

        # Update last interrupt time
        self.last_interrupt_time = current_time

        # First interrupt - try to interrupt current operation
        if self.is_thinking:
            print("\n\n[Interrupting...]")
            try:
                if self.client.is_connected:
                    await self.client.interrupt()
            except ConnectionError as e:
                print(f"[Connection lost during interrupt: {e}]")
            except Exception as e:
                print(f"[Failed to interrupt: {e}]")
        else:
            print("\n\n[Use 'quit' or 'exit' to end the session]")

        print("[Press Ctrl+C again within 2s to exit]")
        return True  # Signal to continue

    async def process_query(self, prompt: str):
        """Process a query and display the response.

        Args:
            prompt: The user's prompt.
        """
        self.is_thinking = True

        try:
            # Send request - messages will be printed by handler callbacks
            # Note: complete_event is created in on_query_start(), not here
            await self.client.send_request(prompt)

            # Wait for completion (no timeout - let the query run as long as needed)
            await self.handler.complete_event.wait()
            print()  # New line after response

            if DEBUG:
                print(f"\n[DEBUG] Completed: {len(self.handler.messages)} messages", flush=True)

        except asyncio.CancelledError:
            # User pressed Ctrl+C during query processing
            # This could happen if the task was cancelled while waiting
            # Ensure the subprocess is interrupted
            print("\n[Interrupted]")
            try:
                if self.client.is_connected:
                    await self.client.interrupt()
            except (ConnectionError, Exception):
                # Best effort - already cancelled, don't worry about errors
                pass

        finally:
            self.is_thinking = False

    async def run(self):
        """Run the async interactive chat loop."""
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║        Async Simple Chat - Event-Driven Architecture        ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print("\nCommands:")
        print("  - Type your message to chat")
        print("  - Type 'quit' or 'exit' to end")
        print("  - Press Ctrl+C once to interrupt current response")
        print("  - Press Ctrl+C twice (within 2s) to exit")
        print()

        try:
            async with self.client:
                print(f"Session ID: {self.client.session_id}")
                print("-" * 60)

                if DEBUG:
                    print(f"[DEBUG] Client connected: {self.client.is_connected}", flush=True)

                while True:
                    try:
                        # Get user input
                        user_input = await asyncio.get_event_loop().run_in_executor(
                            None, input, "\nYou: "
                        )
                        user_input = user_input.strip()

                        if not user_input:
                            continue

                        # Check for exit commands
                        if user_input.lower() in ("quit", "exit", "q"):
                            print("\n👋 Goodbye!")
                            break

                        # Process query
                        await self.process_query(user_input)

                    except KeyboardInterrupt:
                        # User pressed Ctrl+C - handle with double-interrupt detection
                        if not await self.handle_interrupt():
                            return  # Exit on double-interrupt
                        continue

                    except EOFError:
                        # Ctrl+D
                        print("\n\n👋 Goodbye!")
                        break

                    except Exception as e:
                        print(f"\n[Error: {e}]")
                        if DEBUG:
                            import traceback

                            traceback.print_exc()

                            # Check process status
                            if not self.client.is_connected:
                                print(f"[DEBUG] Process is NOT alive", flush=True)
                                stderr_lines = await self.client.get_stderr()
                                print(
                                    f"[DEBUG] Stderr buffer ({len(stderr_lines)} lines):",
                                    flush=True,
                                )
                                for line in stderr_lines[-20:]:  # Show last 20 lines
                                    print(f"  {line}", flush=True)
                            else:
                                print(f"[DEBUG] Process is still alive", flush=True)

                        print("You can try again with a new message.")

        finally:
            print("\n[Session ended. Goodbye!]")


async def main():
    """Main entry point."""
    # Configure options
    options = ClaudeOptions(
        model="haiku",  # Use haiku for faster responses
        system_prompt="You are a friendly and helpful assistant. Keep responses concise.",
    )

    # Create and run chat
    chat = SimpleAsyncChat(options)
    await chat.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
