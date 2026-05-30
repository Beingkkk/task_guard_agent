"""AlertEngine — rule evaluation with cooldown and escalation.

Relates-to: FR-5
"""

import logging
from datetime import datetime

from taskguard.models.alert import Alert
from taskguard.models.snapshot import Snapshot
from taskguard.models.task import Task
from taskguard.storage.metrics_store import MetricsStore

from .rules import BUILTIN_RULES, Rule

logger = logging.getLogger(__name__)


class AlertEngine:
    """Evaluates alert rules with cooldown and escalation support.

    Attributes:
        rules: List of Rule instances to evaluate.
        cooldown_seconds: Minimum seconds between repeated WARNING/INFO alerts.
        escalation_seconds: Seconds before a WARNING alert escalates to CRITICAL.
    """

    def __init__(
        self,
        rules: list[Rule] | None = None,
        cooldown_seconds: int = 300,
        escalation_seconds: int = 1800,
    ) -> None:
        self.rules = rules if rules is not None else list(BUILTIN_RULES)
        self.cooldown_seconds = cooldown_seconds
        self.escalation_seconds = escalation_seconds
        # (alias, rule_name) -> last triggered timestamp
        self._cooldown_state: dict[tuple[str, str], datetime] = {}
        # (alias, rule_name) -> first triggered timestamp (for escalation)
        self._escalation_state: dict[tuple[str, str], datetime] = {}

    def register_rule(self, rule: Rule) -> None:
        """Add a rule to the engine."""
        self.rules.append(rule)

    async def evaluate(self, task: Task, snapshot: Snapshot) -> list[Alert]:
        """Evaluate all rules and return active alerts after applying cooldown/escalation."""
        triggered_rules: list[tuple[str, Alert]] = []

        for rule in self.rules:
            try:
                alert = await rule.evaluate(task, snapshot)
            except Exception:
                logger.exception("Rule %s evaluation failed for %s", rule.name, task.alias)
                continue

            key = (task.alias, rule.name)

            if alert is not None:
                triggered_rules.append((rule.name, alert))
                # Update escalation tracking
                if key not in self._escalation_state:
                    self._escalation_state[key] = alert.timestamp
            else:
                # Rule no longer triggers — clear state
                self._cooldown_state.pop(key, None)
                self._escalation_state.pop(key, None)

        # Apply cooldown and escalation
        results: list[Alert] = []
        for rule_name, alert in triggered_rules:
            key = (task.alias, rule_name)

            # CRITICAL alerts bypass cooldown
            if alert.level == "CRITICAL":
                results.append(alert)
                continue

            # Check escalation
            if alert.level == "WARNING":
                first_triggered = self._escalation_state.get(key)
                if first_triggered is not None:
                    elapsed = (alert.timestamp - first_triggered).total_seconds()
                    if elapsed >= self.escalation_seconds:
                        # Escalate to CRITICAL
                        alert = Alert(
                            rule=alert.rule,
                            level="CRITICAL",
                            message=f"[ESCALATED] {alert.message}",
                            timestamp=alert.timestamp,
                            snapshot=alert.snapshot,
                        )
                        # Reset escalation timer to prevent re-escalation loop
                        self._escalation_state[key] = alert.timestamp

            # CRITICAL alerts bypass cooldown (including after escalation)
            if alert.level == "CRITICAL":
                results.append(alert)
                continue

            # Check cooldown
            last_triggered = self._cooldown_state.get(key)
            if last_triggered is not None:
                elapsed = (alert.timestamp - last_triggered).total_seconds()
                if elapsed < self.cooldown_seconds:
                    continue  # Still in cooldown

            # Alert passes all filters
            results.append(alert)
            self._cooldown_state[key] = alert.timestamp

        return results

    async def evaluate_and_persist(
        self,
        task: Task,
        snapshot: Snapshot,
        metrics_store: MetricsStore | None = None,
    ) -> list[Alert]:
        """Evaluate rules, persist alerts, and return active alerts.

        This is a convenience method that wires the metrics_store into each rule
        evaluation, saves alerts to storage, and attaches them to the snapshot.
        """
        # Evaluate with metrics_store available
        raw_alerts: list[Alert] = []
        for rule in self.rules:
            try:
                alert = await rule.evaluate(task, snapshot, metrics_store)
            except Exception:
                logger.exception("Rule %s evaluation failed for %s", rule.name, task.alias)
                continue

            key = (task.alias, rule.name)

            if alert is not None:
                raw_alerts.append(alert)
                if key not in self._escalation_state:
                    self._escalation_state[key] = alert.timestamp
            else:
                self._cooldown_state.pop(key, None)
                self._escalation_state.pop(key, None)

        # Apply cooldown and escalation
        results: list[Alert] = []
        for alert in raw_alerts:
            key = (task.alias, alert.rule)

            if alert.level == "CRITICAL":
                results.append(alert)
            else:
                # Check escalation
                first_triggered = self._escalation_state.get(key)
                if alert.level == "WARNING" and first_triggered is not None:
                    elapsed = (alert.timestamp - first_triggered).total_seconds()
                    if elapsed >= self.escalation_seconds:
                        alert = Alert(
                            rule=alert.rule,
                            level="CRITICAL",
                            message=f"[ESCALATED] {alert.message}",
                            timestamp=alert.timestamp,
                            snapshot=alert.snapshot,
                        )
                        self._escalation_state[key] = alert.timestamp

                # Check cooldown
                last_triggered = self._cooldown_state.get(key)
                if last_triggered is not None:
                    elapsed = (alert.timestamp - last_triggered).total_seconds()
                    if elapsed < self.cooldown_seconds:
                        continue

                results.append(alert)
                self._cooldown_state[key] = alert.timestamp

        # Persist alerts and attach to snapshot
        snapshot.alerts = results
        if metrics_store is not None:
            for alert in results:
                try:
                    await metrics_store.save_alert(task.alias, alert)
                except Exception:
                    logger.exception("Failed to persist alert for %s", task.alias)

        return results
