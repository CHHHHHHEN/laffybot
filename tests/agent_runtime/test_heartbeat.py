# mypy: disable-error-code="untyped-decorator"
"""Tests for HeartbeatManager."""

from __future__ import annotations

import json

import pytest

from laffybot.agent_runtime.heartbeat import HeartbeatManager


class TestInitialization:
    """HeartbeatManager interval configuration."""

    def test_default_interval_is_set(self) -> None:
        hm = HeartbeatManager()
        assert hm.interval_s == 15

    def test_custom_interval(self) -> None:
        hm = HeartbeatManager(interval_s=10)
        assert hm.interval_s == 10

    def test_env_var_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LAFFYBOT_AGENT_RUNTIME_HEARTBEAT_INTERVAL_S", "30")
        hm = HeartbeatManager()
        assert hm.interval_s == 30

    def test_invalid_env_var_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LAFFYBOT_AGENT_RUNTIME_HEARTBEAT_INTERVAL_S", "abc")
        hm = HeartbeatManager()
        assert hm.interval_s == 15

    def test_env_var_below_minimum_is_clamped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LAFFYBOT_AGENT_RUNTIME_HEARTBEAT_INTERVAL_S", "1")
        hm = HeartbeatManager()
        assert hm.interval_s == 5

    def test_explicit_interval_overrides_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LAFFYBOT_AGENT_RUNTIME_HEARTBEAT_INTERVAL_S", "30")
        hm = HeartbeatManager(interval_s=10)
        assert hm.interval_s == 10


class TestWaitForPingTimeout:
    """wait_for_ping returns a ping string when idle timeout expires."""

    @pytest.mark.asyncio
    async def test_timeout_returns_ping_string(self) -> None:
        hm = HeartbeatManager(interval_s=0.01)
        hm.reset()  # start timer; first wait_for_ping returns None due to init state
        await hm.wait_for_ping()  # consume the init state
        result = await hm.wait_for_ping()
        assert result is not None
        assert result.startswith("event: message\ndata: ")
        assert result.endswith("\n\n")

    @pytest.mark.asyncio
    async def test_ping_contains_valid_json(self) -> None:
        hm = HeartbeatManager(interval_s=0.01)
        hm.reset()
        await hm.wait_for_ping()
        result = await hm.wait_for_ping()
        assert result is not None
        data_str = result[len("event: message\ndata: ") :].rstrip("\n\n")
        parsed = json.loads(data_str)
        assert parsed["type"] == "ping"
        assert "timestamp" in parsed

    @pytest.mark.asyncio
    async def test_consecutive_timeouts(self) -> None:
        hm = HeartbeatManager(interval_s=0.01)
        hm.reset()
        await hm.wait_for_ping()  # consume init state
        for _ in range(3):
            r = await hm.wait_for_ping()
            assert r is not None


class TestWaitForPingReset:
    """wait_for_ping returns None when reset before timeout."""

    @pytest.mark.asyncio
    async def test_reset_returns_none(self) -> None:
        hm = HeartbeatManager(interval_s=5.0)
        hm.reset()
        result = await hm.wait_for_ping()
        assert result is None

    @pytest.mark.asyncio
    async def test_multiple_resets(self) -> None:
        hm = HeartbeatManager(interval_s=5.0)
        for _ in range(3):
            hm.reset()
            r = await hm.wait_for_ping()
            assert r is None

    @pytest.mark.asyncio
    async def test_reset_clears_timer_then_timeout_restarts(self) -> None:
        hm = HeartbeatManager(interval_s=0.01)
        hm.reset()
        await hm.wait_for_ping()  # consume immediate reset return
        r = await hm.wait_for_ping()  # timer restarted → should timeout
        assert r is not None

    @pytest.mark.asyncio
    async def test_alternating_reset_and_timeout(self) -> None:
        hm = HeartbeatManager(interval_s=0.01)
        hm.reset()
        await hm.wait_for_ping()  # reset
        r1 = await hm.wait_for_ping()  # timeout
        assert r1 is not None
        hm.reset()
        r2 = await hm.wait_for_ping()  # reset
        assert r2 is None


class TestStop:
    """stop() marks the manager as stopped."""

    @pytest.mark.asyncio
    async def test_stop_can_be_called(self) -> None:
        hm = HeartbeatManager()
        hm.stop()

    @pytest.mark.asyncio
    async def test_stop_does_not_affect_wait_for_ping(self) -> None:
        hm = HeartbeatManager(interval_s=0.01)
        hm.reset()
        await hm.wait_for_ping()  # consume init state
        hm.stop()
        r = await hm.wait_for_ping()
        assert r is not None


class TestResetEvent:
    """reset() sets internal event, clear() is internal."""

    @pytest.mark.asyncio
    async def test_reset_sets_internal_event(self) -> None:
        hm = HeartbeatManager(interval_s=5.0)
        # Initially _reset_event is set (from __init__)
        r1 = await hm.wait_for_ping()
        assert r1 is None  # returns None because _reset_event was already set
        # Now _reset_event has been cleared (wait_for_ping clears it after returning)
        hm.reset()  # sets it again
        r2 = await hm.wait_for_ping()
        assert r2 is None

    @pytest.mark.asyncio
    async def test_initial_state_returns_none(self) -> None:
        hm = HeartbeatManager(interval_s=5.0)
        # __init__ sets _reset_event, so first wait_for_ping returns None
        r = await hm.wait_for_ping()
        assert r is None
