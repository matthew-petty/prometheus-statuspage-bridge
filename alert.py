"""Alert parsing and severity calculation logic."""

from typing import Any

# Severity hierarchies - higher index = higher severity
IMPACT_ORDER = ["none", "maintenance", "minor", "major", "critical"]
COMPONENT_STATUS_ORDER = [
    "operational",
    "under_maintenance",
    "degraded_performance",
    "partial_outage",
    "major_outage",
]
STATUS_ORDER = ["investigating", "identified", "monitoring", "resolved"]


def get_max_by_order(values: list[str], order: list[str], default: str) -> str:
    """Get the maximum value from a list based on a severity order."""
    if not values:
        return default
    max_index = -1
    max_value = default
    for value in values:
        value_lower = value.lower()
        if value_lower in order:
            index = order.index(value_lower)
            if index > max_index:
                max_index = index
                max_value = value_lower
    return max_value if max_index >= 0 else default


def get_firing_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter to only firing alerts."""
    return [a for a in alerts if a.get("status") == "firing"]


def calculate_severity(alerts: list[dict[str, Any]]) -> dict[str, str]:
    """Calculate max severity values from a list of alerts.

    Returns dict with keys: status, impact_override, component_status
    Component status is calculated only from FIRING alerts.
    """
    firing_alerts = get_firing_alerts(alerts)

    # Status and impact use all alerts
    statuses = [
        a.get("annotations", {}).get("statuspageStatus", "identified")
        for a in alerts
    ]
    impacts = [
        a.get("annotations", {}).get("statuspageImpactOverride", "none")
        for a in alerts
    ]

    # Component status only from FIRING alerts
    component_statuses = [
        a.get("annotations", {}).get("statuspageComponentStatus", "")
        for a in firing_alerts
        if a.get("annotations", {}).get("statuspageComponentStatus")
    ]

    return {
        "status": get_max_by_order(statuses, STATUS_ORDER, "identified"),
        "impact_override": get_max_by_order(impacts, IMPACT_ORDER, "none"),
        "component_status": get_max_by_order(
            component_statuses, COMPONENT_STATUS_ORDER, "partial_outage"
        ),
    }


def build_summary(alerts: list[dict[str, Any]]) -> str:
    """Build a summary from alert annotations."""
    firing_alerts = get_firing_alerts(alerts)
    summaries = []
    for alert in firing_alerts:
        summary = alert.get("annotations", {}).get("statuspageSummary", "")
        if summary and summary not in summaries:
            summaries.append(summary)
    return "\n".join(summaries) if summaries else "Service experiencing issues"


def get_component_name(alerts: list[dict[str, Any]]) -> str:
    """Get component name from alerts."""
    for alert in alerts:
        name = alert.get("annotations", {}).get("statuspageComponentName", "")
        if name:
            return name
    return "Service"
