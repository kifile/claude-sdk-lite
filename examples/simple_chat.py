#!/usr/bin/env python3
"""Simple interactive chat example using ClaudeClient.

This demonstrates a minimal chatbot with:
- Multi-turn conversation
- Context retention
- Double Ctrl+C to exit (single Ctrl+C interrupts)
- "Thinking" state while waiting for response
- Clean exit handling
"""

import os
import sys
import threading
import time

from claude_sdk_lite import ClaudeClient, ClaudeOptions

# Time window for double Ctrl+C to trigger exit
DOUBLE_INTERRUPT_TIMEOUT = 2.0

# Enable debug mode to see all messages
# Set via environment variable CLAUDE_SDK_DEBUG=true for verbose output
DEBUG = os.environ.get("CLAUDE_SDK_DEBUG", "false").lower() == "true"


class SimpleChat:
    """Interactive chat interface with improved UX."""

    def __init__(self, options: ClaudeOptions):
        """Initialize the chat interface.

        Args:
            options: Configuration options for the session.
        """
        self.options = options
        self.client = ClaudeClient(options=options)
        self.last_interrupt_time = None
        self.is_thinking = False

    def handle_interrupt(self):
        """Handle Ctrl+C with double-interrupt detection.

        Returns:
            True if interrupt was handled, False if it's a double-interrupt (exit).
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

        # First interrupt
        if self.is_thinking:
            print("\n\n[Interrupting...]")
            try:
                if self.client.is_connected:
                    self.client.interrupt()
            except Exception as e:
                print(f"[Failed to interrupt: {e}]")
        else:
            print("\n\n[Use 'quit' or 'exit' to end the session]")

        print("[Press Ctrl+C again within 2s to exit]")
        return True  # Signal to continue

    def display_thinking(self, stop_event: threading.Event):
        """Display animated "thinking" indicator.

        Args:
            stop_event: Threading event to stop the animation.
        """
        indicators = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0

        while not stop_event.is_set():
            try:
                print(f"\r{indicators[idx % len(indicators)]} Thinking... ", end="", flush=True)
                idx += 1
                time.sleep(0.1)
            except KeyboardInterrupt:
                break

        # Clear the thinking line
        print("\r" + " " * 40 + "\r", end="", flush=True)

    def process_query(self, prompt: str):
        """Process a query and display the response.

        Args:
            prompt: The user's prompt.
        """
        from claude_sdk_lite.types import (
            AssistantMessage,
            ResultMessage,
            SystemMessage,
            TextBlock,
            ThinkingBlock,
            ToolResultBlock,
            ToolUseBlock,
        )

        # Variables for thread communication
        response_messages = []
        response_complete = threading.Event()
        thinking_stop = threading.Event()

        if DEBUG:
            print(f"\n{'='*60}", flush=True)
            print(f"[DEBUG] Sending query: {prompt[:50]}...", flush=True)
            print(f"{'='*60}", flush=True)

        # Thread to collect messages
        def collect_messages():
            try:
                from claude_sdk_lite.types import AssistantMessage

                msg_count = 0
                for message in self.client.query(prompt):
                    msg_count += 1
                    response_messages.append(message)

                    if DEBUG:
                        type_name = type(message).__name__
                        print(f"\n[DEBUG] Message #{msg_count}:", flush=True)
                        print(f"  - Type: {type_name}", flush=True)
                        print(f"  - Full: {message}", flush=True)

                        if isinstance(message, AssistantMessage):
                            print(f"  - Content blocks: {len(message.content)}", flush=True)
                            for i, block in enumerate(message.content):
                                print(f"    Block {i}: type={block.type}", flush=True)
                                if hasattr(block, "text"):
                                    text_preview = block.text[:100] if block.text else ""
                                    print(f"      text: {text_preview}...", flush=True)
                                if hasattr(block, "name"):
                                    print(f"      name: {block.name}", flush=True)

                    if isinstance(message, ResultMessage):
                        if DEBUG:
                            print(f"\n[DEBUG] Result message received", flush=True)
                            print(f"  - is_error: {message.is_error}", flush=True)
                            print(f"  - result: {message.result}", flush=True)
                        break
            finally:
                thinking_stop.set()
                response_complete.set()

        # Start collection thread
        collector = threading.Thread(target=collect_messages, daemon=True)
        collector.start()

        # Show thinking indicator while waiting
        self.is_thinking = True
        thinking_thread = threading.Thread(
            target=self.display_thinking,
            args=(thinking_stop,),
            daemon=True,
        )
        thinking_thread.start()

        # Wait for first message or completion (with small timeout for fast responses)
        collector.join(timeout=0.5)

        # Stop thinking animation
        thinking_stop.set()
        self.is_thinking = False

        # Wait for thinking thread to finish
        thinking_thread.join(timeout=0.5)

        # IMPORTANT: Wait for collector to finish BEFORE displaying messages
        # This ensures response_messages is fully populated
        response_complete.wait(timeout=30.0)

        if DEBUG:
            print(f"\n{'='*60}", flush=True)
            print(f"[DEBUG] Collected {len(response_messages)} messages", flush=True)
            print(f"{'='*60}", flush=True)

        # Display all collected messages
        print("\nClaude: ", end="", flush=True)

        for message in response_messages:
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text, end="", flush=True)
                    elif isinstance(block, ToolUseBlock):
                        print(f"\n[Tool: {block.name}]", end="", flush=True)
                    elif isinstance(block, ThinkingBlock):
                        print(f"\n[Thinking...]", end="", flush=True)
            elif isinstance(message, SystemMessage):
                # SystemMessage has 'data' field, not 'message'
                print(f"\n[System: {message.data.get('subtype', 'unknown')}]", end="", flush=True)
            elif isinstance(message, ResultMessage):
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

        print()  # New line after response

        if DEBUG and not response_complete.is_set():
            print("\n[DEBUG] Warning: Collector thread did not finish in time", flush=True)

    def run(self):
        """Run the interactive chat loop."""
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║           Simple Chat - Powered by ClaudeClient            ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print("\nCommands:")
        print("  - Type your message to chat")
        print("  - Type 'quit' or 'exit' to end")
        print("  - Press Ctrl+C once to interrupt current response")
        print("  - Press Ctrl+C twice (within 2s) to exit")
        print()

        try:
            with self.client:
                print(f"Session ID: {self.client.session_id}")
                print("-" * 60)

                if DEBUG:
                    print(f"[DEBUG] Client connected: {self.client.is_connected}", flush=True)

                while True:
                    try:
                        # Get user input
                        user_input = input("\nYou: ").strip()

                        if not user_input:
                            continue

                        # Check for exit commands
                        if user_input.lower() in ("quit", "exit", "q"):
                            print("\n👋 Goodbye!")
                            break

                        # Process query
                        self.process_query(user_input)

                    except KeyboardInterrupt:
                        # User pressed Ctrl+C - handle with double-interrupt detection
                        if not self.handle_interrupt():
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
                                stderr_lines = self.client.stderr_output
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


def main():
    """Main entry point."""
    # Configure options
    options = ClaudeOptions(
        model="haiku",  # Use haiku for faster responses
        system_prompt="You are a friendly and helpful assistant. Keep responses concise.",
    )

    # Create and run chat
    chat = SimpleChat(options)
    chat.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
