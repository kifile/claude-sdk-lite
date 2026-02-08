"""Basic usage examples for claude-sdk-lite (async version)."""

import asyncio

from claude_sdk_lite import ClaudeOptions, async_query, async_query_text
from claude_sdk_lite.types import AssistantMessage, ResultMessage, TextBlock


async def example_basic_query():
    """Basic query example."""
    print("=== Basic Query Example (Async) ===\n")

    async for message in async_query(prompt="What is 2 + 2?"):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
        elif isinstance(message, ResultMessage):
            print(f"Cost: ${message.total_cost_usd:.4f}" if message.total_cost_usd else "Cost: N/A")
            print(f"Turns: {message.num_turns}")


async def example_query_text():
    """Simplified text response example."""
    print("\n=== Query Text Example (Async) ===\n")

    response = await async_query_text(prompt="What is the capital of Japan? One word only.")
    print(f"Response: {response.strip()}")


async def example_with_options():
    """Example with options."""
    print("\n=== Example with Options (Async) ===\n")

    options = ClaudeOptions(
        model="haiku",
        system_prompt="You are a helpful assistant",
        max_turns=1,
    )

    response = await async_query_text(prompt="Count from 1 to 3", options=options)
    print(f"Response: {response.strip()}")


async def example_with_thinking():
    """Example showing thinking blocks."""
    print("\n=== Example with Thinking Blocks (Async) ===\n")

    async for message in async_query(prompt="What is 2 + 2?"):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "thinking") and block.thinking:
                    print(f"[Thinking] {block.thinking[:100]}...")
                elif isinstance(block, TextBlock):
                    print(f"Claude: {block.text}")
        elif isinstance(message, ResultMessage):
            print(f"Completed in {message.duration_ms}ms")


async def example_multi_turn():
    """Example multi-turn conversation."""
    print("\n=== Multi-Turn Example (Async) ===\n")

    options = ClaudeOptions(max_turns=2)

    messages = []
    async for message in async_query(
        prompt="Tell me a joke, then explain why it's funny", options=options
    ):
        messages.append(message)

    assistant_messages = [m for m in messages if isinstance(m, AssistantMessage)]
    print(f"Assistant responses: {len(assistant_messages)}")


async def example_concurrent_queries():
    """Example of concurrent async queries."""
    print("\n=== Concurrent Queries Example (Async) ===\n")

    async def get_answer(prompt: str) -> str:
        """Get answer from Claude."""
        return await async_query_text(prompt=prompt, options=ClaudeOptions(model="haiku"))

    # Run multiple queries concurrently
    results = await asyncio.gather(
        get_answer("What is 2 + 2? One word."),
        get_answer("What is 3 + 3? One word."),
        get_answer("What is 4 + 4? One word."),
    )

    for i, result in enumerate(results, 1):
        print(f"Query {i}: {result.strip()}")


async def main():
    """Run all examples."""
    print("Claude SDK Lite - Basic Usage Examples (Async)")
    print("=" * 50)

    await example_basic_query()
    await example_query_text()
    await example_with_options()
    await example_with_thinking()
    await example_multi_turn()
    await example_concurrent_queries()

    print("\n" + "=" * 50)
    print("Examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
