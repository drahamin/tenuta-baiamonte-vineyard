from __future__ import annotations


ALERT_STATES = frozenset({"acknowledged", "resolved", "dismissed"})


def valid_alert_transition(status: object) -> bool:
    """Centralize alert-state validation independently from HTTP routing."""
    return str(status or "") in ALERT_STATES
