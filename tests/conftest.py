"""Shared test fixtures for statuspage-bridge tests."""

import pytest


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


def make_webhook_payload(
    status: str = "firing",
    page_id: str = "test-page-id",
    component_id: str = "test-component-id",
    alerts: list | None = None,
) -> dict:
    """Create an Alertmanager webhook payload."""
    if alerts is None:
        alerts = [make_alert()]
    return {
        "status": status,
        "groupLabels": {
            "statuspagePageId": page_id,
            "statuspageComponentId": component_id,
        },
        "alerts": alerts,
    }


@pytest.fixture
def single_firing_alert():
    """Single firing alert."""
    return make_alert()


@pytest.fixture
def single_resolved_alert():
    """Single resolved alert."""
    return make_alert(status="resolved")


@pytest.fixture
def multiple_firing_alerts():
    """Multiple firing alerts with different severities."""
    return [
        make_alert(
            alertname="LowSeverityAlert",
            statuspage_status="investigating",
            impact_override="minor",
            component_status="degraded_performance",
            summary="Minor issue detected",
        ),
        make_alert(
            alertname="HighSeverityAlert",
            statuspage_status="identified",
            impact_override="major",
            component_status="partial_outage",
            summary="Major issue detected",
        ),
        make_alert(
            alertname="CriticalAlert",
            statuspage_status="identified",
            impact_override="critical",
            component_status="major_outage",
            summary="Critical outage",
        ),
    ]


@pytest.fixture
def mixed_firing_resolved_alerts():
    """Mix of firing and resolved alerts - simulates partial recovery."""
    return [
        make_alert(
            status="firing",
            alertname="StillFiringAlert",
            impact_override="minor",
            component_status="degraded_performance",
            summary="Still having issues",
        ),
        make_alert(
            status="resolved",
            alertname="ResolvedAlert",
            impact_override="critical",
            component_status="major_outage",
            summary="This one recovered",
        ),
    ]


@pytest.fixture
def firing_webhook_payload():
    """Standard firing webhook payload."""
    return make_webhook_payload(status="firing")


@pytest.fixture
def resolved_webhook_payload():
    """Standard resolved webhook payload."""
    return make_webhook_payload(
        status="resolved",
        alerts=[make_alert(status="resolved")],
    )


@pytest.fixture
def multi_alert_firing_payload(multiple_firing_alerts):
    """Webhook with multiple firing alerts of varying severity."""
    return make_webhook_payload(status="firing", alerts=multiple_firing_alerts)


@pytest.fixture
def mixed_alert_payload(mixed_firing_resolved_alerts):
    """Webhook with mix of firing and resolved alerts."""
    return make_webhook_payload(status="firing", alerts=mixed_firing_resolved_alerts)


@pytest.fixture
def sample_unresolved_incident():
    """Sample unresolved incident from Statuspage API."""
    return {
        "id": "incident-123",
        "name": "Test Component - Incident",
        "status": "identified",
        "impact": "major",
        "components": [
            {"id": "test-component-id", "name": "Test Component"},
        ],
    }


@pytest.fixture
def sample_unresolved_incidents_response(sample_unresolved_incident):
    """List of unresolved incidents from Statuspage API."""
    return [sample_unresolved_incident]
