"""Tests for AlertEngine cooldown, escalation, and recovery.

Relates-to: FR-5
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from taskguard.alerters.engine import AlertEngine
from taskguard.models.alert import Alert
from taskguard.models.snapshot import Snapshot
from taskguard.models.task import Task


class TestAlertEngineCooldown:
    @pytest.mark.asyncio
    async def test_cooldown_suppresses_repeat(self) -> None:
        """Same rule within cooldown should not fire again."""
        engine = AlertEngine(cooldown_seconds=300)
        rule = MagicMock()
        rule.name = "test_rule"
        rule.evaluate = AsyncMock(
            return_value=Alert(
                rule="test_rule",
                level="WARNING",
                message="test",
                timestamp=datetime.now(UTC),
            )
        )
        engine.register_rule(rule)

        task = Task(alias="t", pid=1)
        snapshot = Snapshot(task_alias="t", log_lines=[])

        # First call: should fire
        alerts1 = await engine.evaluate(task, snapshot)
        assert len(alerts1) == 1

        # Second call immediately: should be suppressed
        alerts2 = await engine.evaluate(task, snapshot)
        assert len(alerts2) == 0

    @pytest.mark.asyncio
    async def test_cooldown_expires(self) -> None:
        """After cooldown period, rule can fire again."""
        engine = AlertEngine(cooldown_seconds=1)
        rule = MagicMock()
        rule.name = "test_rule"
        rule.evaluate = AsyncMock(
            return_value=Alert(
                rule="test_rule",
                level="WARNING",
                message="test",
                timestamp=datetime.now(UTC),
            )
        )
        engine.register_rule(rule)

        task = Task(alias="t", pid=1)
        snapshot = Snapshot(task_alias="t", log_lines=[])

        alerts1 = await engine.evaluate(task, snapshot)
        assert len(alerts1) == 1

        # Manually set cooldown state to past
        engine._cooldown_state[("t", "test_rule")] = datetime.now(UTC) - timedelta(seconds=2)

        alerts2 = await engine.evaluate(task, snapshot)
        assert len(alerts2) == 1

    @pytest.mark.asyncio
    async def test_critical_bypasses_cooldown(self) -> None:
        """CRITICAL alerts are not subject to cooldown."""
        engine = AlertEngine(cooldown_seconds=300)
        rule = MagicMock()
        rule.name = "critical_rule"
        rule.evaluate = AsyncMock(
            return_value=Alert(
                rule="critical_rule",
                level="CRITICAL",
                message="critical",
                timestamp=datetime.now(UTC),
            )
        )
        engine.register_rule(rule)

        task = Task(alias="t", pid=1)
        snapshot = Snapshot(task_alias="t", log_lines=[])

        alerts1 = await engine.evaluate(task, snapshot)
        assert len(alerts1) == 1

        alerts2 = await engine.evaluate(task, snapshot)
        assert len(alerts2) == 1  # Still fires because CRITICAL

    @pytest.mark.asyncio
    async def test_independent_cooldown_per_rule(self) -> None:
        """Different rules have independent cooldown timers."""
        engine = AlertEngine(cooldown_seconds=300)

        rule1 = MagicMock()
        rule1.name = "rule1"
        rule1.evaluate = AsyncMock(
            return_value=Alert(
                rule="rule1", level="WARNING", message="m1", timestamp=datetime.now(UTC)
            )
        )
        rule2 = MagicMock()
        rule2.name = "rule2"
        rule2.evaluate = AsyncMock(
            return_value=Alert(
                rule="rule2", level="WARNING", message="m2", timestamp=datetime.now(UTC)
            )
        )
        engine.register_rule(rule1)
        engine.register_rule(rule2)

        task = Task(alias="t", pid=1)
        snapshot = Snapshot(task_alias="t", log_lines=[])

        alerts = await engine.evaluate(task, snapshot)
        assert len(alerts) == 2  # Both fire

        # Second call: both suppressed by cooldown
        alerts = await engine.evaluate(task, snapshot)
        assert len(alerts) == 0


class TestAlertEngineEscalation:
    @pytest.mark.asyncio
    async def test_escalation_after_duration(self) -> None:
        """WARNING alert escalates to CRITICAL after escalation_time."""
        engine = AlertEngine(
            cooldown_seconds=300,
            escalation_seconds=1800,
        )
        rule = MagicMock()
        rule.name = "test_rule"
        rule.evaluate = AsyncMock(
            return_value=Alert(
                rule="test_rule",
                level="WARNING",
                message="warning",
                timestamp=datetime.now(UTC),
            )
        )
        engine.register_rule(rule)

        task = Task(alias="t", pid=1)
        snapshot = Snapshot(task_alias="t", log_lines=[])

        # First fire: WARNING
        alerts1 = await engine.evaluate(task, snapshot)
        assert alerts1[0].level == "WARNING"

        # Set escalation state to past
        engine._escalation_state[("t", "test_rule")] = datetime.now(UTC) - timedelta(seconds=1900)

        # Next fire: should be escalated to CRITICAL
        alerts2 = await engine.evaluate(task, snapshot)
        assert len(alerts2) == 1
        assert alerts2[0].level == "CRITICAL"
        assert "escalated" in alerts2[0].message.lower() or "升级" in alerts2[0].message

    @pytest.mark.asyncio
    async def test_no_escalation_before_time(self) -> None:
        """Before escalation_time, WARNING stays WARNING."""
        engine = AlertEngine(
            cooldown_seconds=300,
            escalation_seconds=1800,
        )
        rule = MagicMock()
        rule.name = "test_rule"
        rule.evaluate = AsyncMock(
            return_value=Alert(
                rule="test_rule",
                level="WARNING",
                message="warning",
                timestamp=datetime.now(UTC),
            )
        )
        engine.register_rule(rule)

        task = Task(alias="t", pid=1)
        snapshot = Snapshot(task_alias="t", log_lines=[])

        # Set escalation state to recent (just started)
        engine._escalation_state[("t", "test_rule")] = datetime.now(UTC) - timedelta(seconds=60)

        alerts = await engine.evaluate(task, snapshot)
        assert alerts[0].level == "WARNING"

    @pytest.mark.asyncio
    async def test_critical_not_escalated(self) -> None:
        """CRITICAL rules don't participate in escalation."""
        engine = AlertEngine(escalation_seconds=1800)
        rule = MagicMock()
        rule.name = "crit_rule"
        rule.evaluate = AsyncMock(
            return_value=Alert(
                rule="crit_rule",
                level="CRITICAL",
                message="critical",
                timestamp=datetime.now(UTC),
            )
        )
        engine.register_rule(rule)

        task = Task(alias="t", pid=1)
        snapshot = Snapshot(task_alias="t", log_lines=[])

        alerts1 = await engine.evaluate(task, snapshot)
        assert alerts1[0].level == "CRITICAL"

        # Still CRITICAL, not "upgraded"
        engine._escalation_state[("t", "crit_rule")] = datetime.now(UTC) - timedelta(seconds=3600)
        alerts2 = await engine.evaluate(task, snapshot)
        assert alerts2[0].level == "CRITICAL"


class TestAlertEngineRecovery:
    @pytest.mark.asyncio
    async def test_recovery_clears_state(self) -> None:
        """When rule stops firing, cooldown and escalation states are cleared."""
        engine = AlertEngine(cooldown_seconds=300, escalation_seconds=1800)
        rule = MagicMock()
        rule.name = "test_rule"
        rule.evaluate = AsyncMock(
            return_value=Alert(
                rule="test_rule",
                level="WARNING",
                message="warning",
                timestamp=datetime.now(UTC),
            )
        )
        engine.register_rule(rule)

        task = Task(alias="t", pid=1)
        snapshot = Snapshot(task_alias="t", log_lines=[])

        # Fire once
        await engine.evaluate(task, snapshot)
        assert ("t", "test_rule") in engine._cooldown_state
        assert ("t", "test_rule") in engine._escalation_state

        # Now rule stops firing (returns None)
        rule.evaluate = AsyncMock(return_value=None)
        await engine.evaluate(task, snapshot)

        # States should be cleared
        assert ("t", "test_rule") not in engine._cooldown_state
        assert ("t", "test_rule") not in engine._escalation_state

    @pytest.mark.asyncio
    async def test_recovery_allows_re_trigger(self) -> None:
        """After recovery, rule can immediately fire again."""
        engine = AlertEngine(cooldown_seconds=300)
        rule = MagicMock()
        rule.name = "test_rule"

        # First: fires
        rule.evaluate = AsyncMock(
            return_value=Alert(
                rule="test_rule",
                level="WARNING",
                message="warning",
                timestamp=datetime.now(UTC),
            )
        )
        engine.register_rule(rule)

        task = Task(alias="t", pid=1)
        snapshot = Snapshot(task_alias="t", log_lines=[])

        await engine.evaluate(task, snapshot)

        # Then: stops firing
        rule.evaluate = AsyncMock(return_value=None)
        await engine.evaluate(task, snapshot)

        # Then: fires again
        rule.evaluate = AsyncMock(
            return_value=Alert(
                rule="test_rule",
                level="WARNING",
                message="warning again",
                timestamp=datetime.now(UTC),
            )
        )
        alerts = await engine.evaluate(task, snapshot)
        assert len(alerts) == 1  # Not suppressed by old cooldown
