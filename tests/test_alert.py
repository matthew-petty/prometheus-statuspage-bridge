"""Tests for alert parsing and severity calculation logic."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from alert import (
    IMPACT_ORDER,
    COMPONENT_STATUS_ORDER,
    STATUS_ORDER,
    get_max_by_order,
    get_firing_alerts,
    calculate_severity,
    build_summary,
    get_component_name,
)


def make_alert(
    status: str = "firing",
    alertname: str = "TestAlert",
    tenant: str = "test-tenant",
    component_name: str = "Test Component",
    statuspage_status: str = "identified",
    impact_override: str = "minor",
    component_status: str = "partial_outage",
    summary: str = "Test alert summary",
) -> dict:
    """Create a single alert dict with customizable fields."""
    return {
        "status": status,
        "labels": {
            "alertname": alertname,
            "tenant": tenant,
        },
        "annotations": {
            "statuspageComponentName": component_name,
            "statuspageStatus": statuspage_status,
            "statuspageImpactOverride": impact_override,
            "statuspageComponentStatus": component_status,
            "statuspageSummary": summary,
        },
    }


class TestGetMaxByOrder:
    """Tests for get_max_by_order function."""

    def test_single_value(self):
        """Single value returns that value."""
        result = get_max_by_order(["minor"], IMPACT_ORDER, "none")
        assert result == "minor"

    def test_multiple_values_returns_highest(self):
        """Multiple values returns highest severity."""
        result = get_max_by_order(
            ["minor", "critical", "major"], IMPACT_ORDER, "none"
        )
        assert result == "critical"

    def test_empty_list_returns_default(self):
        """Empty list returns default value."""
        result = get_max_by_order([], IMPACT_ORDER, "none")
        assert result == "none"

    def test_unknown_values_returns_default(self):
        """Unknown values are ignored, returns default if all unknown."""
        result = get_max_by_order(["unknown", "invalid"], IMPACT_ORDER, "none")
        assert result == "none"

    def test_mixed_known_unknown_values(self):
        """Mix of known and unknown values returns highest known."""
        result = get_max_by_order(
            ["unknown", "minor", "invalid", "major"], IMPACT_ORDER, "none"
        )
        assert result == "major"

    def test_case_insensitive(self):
        """Values are matched case-insensitively."""
        result = get_max_by_order(["MAJOR", "Minor"], IMPACT_ORDER, "none")
        assert result == "major"

    def test_component_status_order(self):
        """Test with component status hierarchy."""
        result = get_max_by_order(
            ["degraded_performance", "partial_outage", "operational"],
            COMPONENT_STATUS_ORDER,
            "operational",
        )
        assert result == "partial_outage"

    def test_status_order(self):
        """Test with incident status hierarchy."""
        result = get_max_by_order(
            ["investigating", "identified", "monitoring"],
            STATUS_ORDER,
            "investigating",
        )
        assert result == "monitoring"


class TestGetFiringAlerts:
    """Tests for get_firing_alerts function."""

    def test_all_firing(self):
        """All firing alerts are returned."""
        alerts = [
            make_alert(status="firing"),
            make_alert(status="firing"),
        ]
        result = get_firing_alerts(alerts)
        assert len(result) == 2

    def test_all_resolved(self):
        """No alerts returned when all resolved."""
        alerts = [
            make_alert(status="resolved"),
            make_alert(status="resolved"),
        ]
        result = get_firing_alerts(alerts)
        assert len(result) == 0

    def test_mixed_returns_only_firing(self):
        """Only firing alerts returned from mixed list."""
        alerts = [
            make_alert(status="firing", alertname="Firing1"),
            make_alert(status="resolved", alertname="Resolved1"),
            make_alert(status="firing", alertname="Firing2"),
        ]
        result = get_firing_alerts(alerts)
        assert len(result) == 2
        assert all(a["status"] == "firing" for a in result)

    def test_empty_list(self):
        """Empty list returns empty list."""
        result = get_firing_alerts([])
        assert result == []


class TestCalculateSeverity:
    """Tests for calculate_severity function."""

    def test_single_alert(self, single_firing_alert):
        """Single alert returns its severity values."""
        result = calculate_severity([single_firing_alert])
        assert result["status"] == "identified"
        assert result["impact_override"] == "minor"
        assert result["component_status"] == "partial_outage"

    def test_multiple_alerts_returns_max(self, multiple_firing_alerts):
        """Multiple alerts returns maximum severity for each field."""
        result = calculate_severity(multiple_firing_alerts)
        # Critical > major > minor
        assert result["impact_override"] == "critical"
        # major_outage > partial_outage > degraded_performance
        assert result["component_status"] == "major_outage"
        # identified > investigating (by ordinal in STATUS_ORDER)
        assert result["status"] == "identified"

    def test_component_status_from_firing_only(self, mixed_firing_resolved_alerts):
        """Component status is calculated only from FIRING alerts."""
        # The resolved alert has critical/major_outage but should be ignored
        # The firing alert has minor/degraded_performance
        result = calculate_severity(mixed_firing_resolved_alerts)
        assert result["component_status"] == "degraded_performance"

    def test_status_and_impact_from_all_alerts(self, mixed_firing_resolved_alerts):
        """Status and impact use all alerts, not just firing."""
        result = calculate_severity(mixed_firing_resolved_alerts)
        # Impact should consider the resolved alert's critical value
        assert result["impact_override"] == "critical"

    def test_missing_annotations_uses_defaults(self):
        """Missing annotations use default values."""
        alert = {
            "status": "firing",
            "labels": {},
            "annotations": {},
        }
        result = calculate_severity([alert])
        assert result["status"] == "identified"
        assert result["impact_override"] == "none"
        # Default for component_status when no firing alerts have it
        assert result["component_status"] == "partial_outage"

    def test_escalation_scenario(self):
        """Simulate alert escalation - new critical alert joins existing minor."""
        existing_alert = make_alert(
            alertname="ExistingAlert",
            impact_override="minor",
            component_status="degraded_performance",
        )
        new_critical_alert = make_alert(
            alertname="NewCriticalAlert",
            impact_override="critical",
            component_status="major_outage",
        )
        result = calculate_severity([existing_alert, new_critical_alert])
        assert result["impact_override"] == "critical"
        assert result["component_status"] == "major_outage"

    def test_partial_recovery_scenario(self):
        """Simulate partial recovery - critical resolves, minor still firing."""
        still_firing = make_alert(
            status="firing",
            alertname="MinorAlert",
            impact_override="minor",
            component_status="degraded_performance",
        )
        recovered = make_alert(
            status="resolved",
            alertname="CriticalAlert",
            impact_override="critical",
            component_status="major_outage",
        )
        result = calculate_severity([still_firing, recovered])
        # Component status should reflect only the firing alert
        assert result["component_status"] == "degraded_performance"
        # But impact still considers all for historical context
        assert result["impact_override"] == "critical"


class TestBuildSummary:
    """Tests for build_summary function."""

    def test_single_alert(self, single_firing_alert):
        """Single alert returns its summary."""
        result = build_summary([single_firing_alert])
        assert result == "Test alert summary"

    def test_multiple_alerts_concatenates(self, multiple_firing_alerts):
        """Multiple alerts have summaries concatenated."""
        result = build_summary(multiple_firing_alerts)
        assert "Minor issue detected" in result
        assert "Major issue detected" in result
        assert "Critical outage" in result

    def test_deduplicates_identical_summaries(self):
        """Identical summaries are deduplicated."""
        alerts = [
            make_alert(summary="Same summary"),
            make_alert(summary="Same summary"),
            make_alert(summary="Different summary"),
        ]
        result = build_summary(alerts)
        # Should only appear once
        assert result.count("Same summary") == 1
        assert "Different summary" in result

    def test_only_firing_alerts(self, mixed_firing_resolved_alerts):
        """Only firing alerts contribute to summary."""
        result = build_summary(mixed_firing_resolved_alerts)
        assert "Still having issues" in result
        assert "This one recovered" not in result

    def test_empty_alerts_returns_default(self):
        """Empty alerts returns default message."""
        result = build_summary([])
        assert result == "Service experiencing issues"

    def test_missing_summary_annotation(self):
        """Alert without summary annotation is skipped."""
        alerts = [
            {"status": "firing", "annotations": {}},
            make_alert(summary="Has summary"),
        ]
        result = build_summary(alerts)
        assert result == "Has summary"


class TestGetComponentName:
    """Tests for get_component_name function."""

    def test_returns_component_name(self, single_firing_alert):
        """Returns component name from alert."""
        result = get_component_name([single_firing_alert])
        assert result == "Test Component"

    def test_returns_first_found(self):
        """Returns first component name found."""
        alerts = [
            make_alert(component_name="First Component"),
            make_alert(component_name="Second Component"),
        ]
        result = get_component_name(alerts)
        assert result == "First Component"

    def test_skips_empty_names(self):
        """Skips alerts with empty component name."""
        alerts = [
            {"status": "firing", "annotations": {"statuspageComponentName": ""}},
            make_alert(component_name="Valid Name"),
        ]
        result = get_component_name(alerts)
        assert result == "Valid Name"

    def test_returns_default_if_none_found(self):
        """Returns 'Service' if no component name found."""
        alerts = [{"status": "firing", "annotations": {}}]
        result = get_component_name(alerts)
        assert result == "Service"

    def test_empty_list_returns_default(self):
        """Empty list returns default."""
        result = get_component_name([])
        assert result == "Service"
