"""Cancellation support for agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field


class CancelledError(Exception):
    """Raised when a request is cancelled."""

    def __init__(self, reason: str | None = None):
        self.reason = reason
        super().__init__(reason or "Request cancelled")


@dataclass(slots=True)
class CancellationToken:
    """Token for propagating cancellation requests.

    Usage:
        token = CancellationToken()

        # In cancellation handler:
        token.cancel("User requested cancellation")

        # In execution code:
        token.check()  # Raises CancelledError if cancelled

        # Or check without raising:
        if token.is_cancelled:
            # Handle cancellation
    """

    _cancelled: bool = field(default=False, init=False)
    _reason: str | None = field(default=None, init=False)

    def cancel(self, reason: str | None = None) -> None:
        """Mark the token as cancelled.

        Args:
            reason: Optional reason for cancellation.
        """
        self._cancelled = True
        self._reason = reason

    def check(self) -> None:
        """Check if cancelled, raising CancelledError if so.

        Raises:
            CancelledError: If the token has been cancelled.
        """
        if self._cancelled:
            raise CancelledError(self._reason)

    @property
    def is_cancelled(self) -> bool:
        """Check if cancelled without raising."""
        return self._cancelled

    @property
    def reason(self) -> str | None:
        """Get the cancellation reason, if any."""
        return self._reason
