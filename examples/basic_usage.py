"""Basic usage examples for claude-sdk-lite (sync version)."""

from claude_sdk_lite import ClaudeOptions, query, query_text
from claude_sdk_lite.types import AssistantMessage, ResultMessage, TextBlock


def example_basic_query():
    """Basic query example."""
    print("=== Basic Query Example ===\n")

    for message in query(prompt="What is 2 + 2?"):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
        elif isinstance(message, ResultMessage):
            print(f"Cost: ${message.total_cost_usd:.4f}" if message.total_cost_usd else "Cost: N/A")
            print(f"Turns: {message.num_turns}")


def example_query_text():
    """Simplified text response example."""
    print("\n=== Query Text Example ===\n")

    response = query_text(prompt="What is the capital of Japan? One word only.")
    print(f"Response: {response.strip()}")


def example_with_options():
    """Example with options."""
    print("\n=== Example with Options ===\n")

    options = ClaudeOptions(
        model="haiku",
        system_prompt="You are a helpful assistant",
        max_turns=1,
    )

    response = query_text(prompt="Count from 1 to 3", options=options)
    print(f"Response: {response.strip()}")


def example_with_thinking():
    """Example showing thinking blocks."""
    print("\n=== Example with Thinking Blocks ===\n")

    for message in query(prompt="What is 2 + 2?"):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "thinking") and block.thinking:
                    print(f"[Thinking] {block.thinking[:100]}...")
                elif isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
        elif isinstance(message, ResultMessage):
            print(f"Completed in {message.duration_ms}ms")


def example_multi_turn():
    """Example multi-turn conversation."""
    print("\n=== Multi-Turn Example ===\n")

    options = ClaudeOptions(max_turns=2)

    messages = list(query(prompt="Tell me a joke, then explain why it's funny", options=options))

    assistant_messages = [m for m in messages if isinstance(m, AssistantMessage)]
    print(f"Assistant responses: {len(assistant_messages)}")


def main():
    """Run all examples."""
    print("Claude SDK Lite - Basic Usage Examples (Sync)")
    print("=" * 50)

    example_basic_query()
    example_query_text()
    example_with_options()
    example_with_thinking()
    example_multi_turn()

    print("\n" + "=" * 50)
    print("Examples completed!")


if __name__ == "__main__":
    main()
