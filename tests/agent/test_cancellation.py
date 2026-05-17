"""Tests for cancellation mechanism."""

import pytest

from laffybot.agent.cancellation import CancellationToken, CancelledError


def test_token_starts_not_cancelled() -> None:
    token = CancellationToken()
    assert not token.is_cancelled
    token.check()  # should not raise


def test_cancel_marks_token() -> None:
    token = CancellationToken()
    token.cancel("User requested stop")
    assert token.is_cancelled
    assert token.reason == "User requested stop"


def test_check_raises_after_cancel() -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(CancelledError):
        token.check()


def test_cancel_without_reason() -> None:
    token = CancellationToken()
    token.cancel()
    assert token.is_cancelled
    assert token.reason is None


def test_cancelled_error_reason() -> None:
    exc = CancelledError("timeout")
    assert exc.reason == "timeout"
    assert str(exc) == "timeout"


def test_cancelled_error_default_reason() -> None:
    exc = CancelledError()
    assert exc.reason is None
    assert str(exc) == "Request cancelled"


def test_double_cancel_overwrites_reason() -> None:
    token = CancellationToken()
    token.cancel("first")
    token.cancel("second")
    assert token.reason == "second"


def test_multiple_tokens_independent() -> None:
    a = CancellationToken()
    b = CancellationToken()
    a.cancel("stop a")
    assert a.is_cancelled
    assert not b.is_cancelled
    b.check()  # should not raise
