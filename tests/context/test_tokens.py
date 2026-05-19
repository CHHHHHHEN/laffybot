"""Tests for context token counting."""

from laffybot.context.tokens import ApproximateTokenCounter, UsageBasedTokenCounter


def test_approximate_token_counter() -> None:
    counter = ApproximateTokenCounter()
    text = "Hello, world!"
    count = counter.count_tokens(text)
    assert isinstance(count, int)
    assert count > 0


def test_usage_based_token_counter() -> None:
    counter = UsageBasedTokenCounter()
    text = "Hello, world!"
    count = counter.count_tokens(text)
    assert isinstance(count, int)
    assert count > 0


def test_approximate_count_message_tokens() -> None:
    counter = ApproximateTokenCounter()
    message = {"role": "user", "content": "Hello"}
    count = counter.count_message_tokens(message)
    assert isinstance(count, int)
    assert count > 0


def test_usage_based_count_message_tokens() -> None:
    counter = UsageBasedTokenCounter()
    message = {"role": "user", "content": "Hello"}
    count = counter.count_message_tokens(message)
    assert isinstance(count, int)
    assert count > 0
