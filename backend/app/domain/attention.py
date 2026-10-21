"""
Attention / SLA logic for the "what needs attention" overview.

Pure functions that determine whether a work item is stale, overdue,
or otherwise requires immediate focus. No I/O.

The key insight: `attention_due_at` is a **stored, indexed field** on the
item document, recomputed on every event. Finding forgotten work is an
index range scan (`attention_due_at < now AND status IN active`), not a
computation over the dataset. No scheduled jobs needed.
"""

from __future__ import annotations

from datetime import timedelta

from app.domain.enums import ItemPriority, ItemStatus


# SLA windows per priority level
SLA_WINDOWS: dict[ItemPriority, timedelta] = {
    ItemPriority.P0: timedelta(hours=1),
    ItemPriority.P1: timedelta(hours=4),
    ItemPriority.P2: timedelta(hours=24),
    ItemPriority.P3: timedelta(hours=72),
}

# Blocked items are capped at 24 hours regardless of priority
BLOCKED_CAP = timedelta(hours=24)


def sla_window(priority: ItemPriority, status: ItemStatus) -> timedelta:
    """
    Return the SLA window for a given priority and status.
    Blocked items have their window capped at 24 hours.
    """
    window = SLA_WINDOWS.get(priority, timedelta(hours=24))
    if status == ItemStatus.BLOCKED:
        window = min(window, BLOCKED_CAP)
    return window


def calculate_attention_due_at(
    priority: ItemPriority,
    status: ItemStatus,
    base_time = None,
):
    """
    Calculate the timestamp when this item becomes stale or requires urgent attention.
    """
    from datetime import datetime, timezone
    base = base_time or datetime.now(timezone.utc)
    return base + sla_window(priority, status)
