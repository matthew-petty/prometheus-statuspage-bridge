"""Tests for Flask webhook endpoints."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set required env var before importing app
os.environ["STATUSPAGE_API_KEY"] = "test-api-key"

from app import app


def make_alert(
    status: str = "firing",
    alertname: str = "TestAlert",
    component_name: str = "Test Component",
    statuspage_status: str = "identified",
    impact_override: str = "minor",
    component_status: str = "partial_outage",
    summary: str = "Test alert summary",
) -> dict:
    """Create a single alert dict."""
    return {
        "status": status,
        "labels": {"alertname": alertname},
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
    page_id: str = "page-123",
    component_id: str = "comp-456",
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
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_statuspage():
    """Mock StatuspageClient for all tests."""
    with patch("app.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        yield mock_client


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_returns_ok(self, client):
        """Health endpoint returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.data == b"OK"


class TestAlertEndpointValidation:
    """Tests for /alert endpoint input validation."""

    def test_empty_payload_returns_400(self, client):
        """Empty payload returns 400."""
        response = client.post(
            "/alert",
            data="",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_missing_page_id_returns_400(self, client, mock_statuspage):
        """Missing statuspagePageId returns 400."""
        payload = make_webhook_payload()
        del payload["groupLabels"]["statuspagePageId"]

        response = client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 400
        assert b"Missing required group labels" in response.data

    def test_missing_component_id_returns_400(self, client, mock_statuspage):
        """Missing statuspageComponentId returns 400."""
        payload = make_webhook_payload()
        del payload["groupLabels"]["statuspageComponentId"]

        response = client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 400


class TestAlertFiringCreatesIncident:
    """Tests for creating new incidents on firing alerts."""

    def test_creates_incident_when_none_exists(self, client, mock_statuspage):
        """Creates new incident when no existing incident for component."""
        mock_statuspage.find_incident_for_component.return_value = None
        mock_statuspage.create_incident.return_value = {"id": "new-incident"}

        payload = make_webhook_payload(status="firing")
        response = client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200
        mock_statuspage.create_incident.assert_called_once()

        # Verify the call arguments
        call_kwargs = mock_statuspage.create_incident.call_args.kwargs
        assert call_kwargs["page_id"] == "page-123"
        assert call_kwargs["component_id"] == "comp-456"
        assert call_kwargs["status"] == "identified"
        assert call_kwargs["impact_override"] == "minor"
        assert call_kwargs["component_status"] == "partial_outage"

    def test_does_not_resolve_when_creating(self, client, mock_statuspage):
        """Does not call resolve when creating new incident."""
        mock_statuspage.find_incident_for_component.return_value = None
        mock_statuspage.create_incident.return_value = {"id": "new-incident"}

        payload = make_webhook_payload(status="firing")
        client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        mock_statuspage.resolve_incident.assert_not_called()


class TestAlertFiringUpdatesExistingIncident:
    """Tests for updating existing incidents with new alerts."""

    def test_updates_existing_incident(self, client, mock_statuspage):
        """Updates existing incident when one exists for component."""
        existing_incident = {"id": "existing-incident"}
        mock_statuspage.find_incident_for_component.return_value = existing_incident
        mock_statuspage.update_incident.return_value = existing_incident

        payload = make_webhook_payload(status="firing")
        response = client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200
        mock_statuspage.update_incident.assert_called_once()
        mock_statuspage.create_incident.assert_not_called()

        # Verify correct incident ID used
        call_kwargs = mock_statuspage.update_incident.call_args.kwargs
        assert call_kwargs["incident_id"] == "existing-incident"

    def test_new_alert_escalates_severity(self, client, mock_statuspage):
        """New critical alert escalates incident severity."""
        existing_incident = {"id": "existing-incident"}
        mock_statuspage.find_incident_for_component.return_value = existing_incident
        mock_statuspage.update_incident.return_value = existing_incident

        # Simulate: existing minor alert + new critical alert
        alerts = [
            make_alert(
                alertname="ExistingMinor",
                impact_override="minor",
                component_status="degraded_performance",
            ),
            make_alert(
                alertname="NewCritical",
                impact_override="critical",
                component_status="major_outage",
            ),
        ]
        payload = make_webhook_payload(status="firing", alerts=alerts)

        response = client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200

        # Verify escalated severity
        call_kwargs = mock_statuspage.update_incident.call_args.kwargs
        assert call_kwargs["impact_override"] == "critical"
        assert call_kwargs["component_status"] == "major_outage"

    def test_multiple_alerts_uses_highest_severity(self, client, mock_statuspage):
        """Multiple firing alerts use highest severity values."""
        existing_incident = {"id": "existing-incident"}
        mock_statuspage.find_incident_for_component.return_value = existing_incident
        mock_statuspage.update_incident.return_value = existing_incident

        alerts = [
            make_alert(
                alertname="Alert1",
                impact_override="minor",
                component_status="degraded_performance",
                statuspage_status="investigating",
            ),
            make_alert(
                alertname="Alert2",
                impact_override="major",
                component_status="partial_outage",
                statuspage_status="identified",
            ),
            make_alert(
                alertname="Alert3",
                impact_override="critical",
                component_status="major_outage",
                statuspage_status="monitoring",
            ),
        ]
        payload = make_webhook_payload(status="firing", alerts=alerts)

        client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        call_kwargs = mock_statuspage.update_incident.call_args.kwargs
        assert call_kwargs["impact_override"] == "critical"
        assert call_kwargs["component_status"] == "major_outage"
        # monitoring > identified > investigating in STATUS_ORDER
        assert call_kwargs["status"] == "monitoring"


class TestAlertPartialRecovery:
    """Tests for partial recovery scenarios (some alerts resolved)."""

    def test_component_status_from_firing_only(self, client, mock_statuspage):
        """Component status reflects only still-firing alerts."""
        existing_incident = {"id": "existing-incident"}
        mock_statuspage.find_incident_for_component.return_value = existing_incident
        mock_statuspage.update_incident.return_value = existing_incident

        # Critical alert resolved, minor still firing
        alerts = [
            make_alert(
                status="firing",
                alertname="StillFiring",
                impact_override="minor",
                component_status="degraded_performance",
            ),
            make_alert(
                status="resolved",
                alertname="Recovered",
                impact_override="critical",
                component_status="major_outage",
            ),
        ]
        # Overall status is still "firing" because not all alerts resolved
        payload = make_webhook_payload(status="firing", alerts=alerts)

        client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        call_kwargs = mock_statuspage.update_incident.call_args.kwargs
        # Component status should be from firing alert only
        assert call_kwargs["component_status"] == "degraded_performance"
        # Impact considers all alerts for historical context
        assert call_kwargs["impact_override"] == "critical"


class TestAlertResolved:
    """Tests for resolving incidents."""

    def test_resolves_existing_incident(self, client, mock_statuspage):
        """Resolves incident when all alerts resolved."""
        existing_incident = {"id": "existing-incident"}
        mock_statuspage.find_incident_for_component.return_value = existing_incident
        mock_statuspage.resolve_incident.return_value = {
            "id": "existing-incident",
            "status": "resolved",
        }

        payload = make_webhook_payload(
            status="resolved",
            alerts=[make_alert(status="resolved")],
        )
        response = client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200
        mock_statuspage.resolve_incident.assert_called_once()

        call_kwargs = mock_statuspage.resolve_incident.call_args.kwargs
        assert call_kwargs["page_id"] == "page-123"
        assert call_kwargs["incident_id"] == "existing-incident"
        assert call_kwargs["component_id"] == "comp-456"

    def test_handles_no_incident_to_resolve(self, client, mock_statuspage):
        """Gracefully handles resolved with no open incident."""
        mock_statuspage.find_incident_for_component.return_value = None

        payload = make_webhook_payload(
            status="resolved",
            alerts=[make_alert(status="resolved")],
        )
        response = client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        # Should succeed without error
        assert response.status_code == 200
        mock_statuspage.resolve_incident.assert_not_called()

    def test_does_not_create_on_resolved(self, client, mock_statuspage):
        """Does not create incident when status is resolved."""
        mock_statuspage.find_incident_for_component.return_value = None

        payload = make_webhook_payload(
            status="resolved",
            alerts=[make_alert(status="resolved")],
        )
        client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        mock_statuspage.create_incident.assert_not_called()
        mock_statuspage.update_incident.assert_not_called()


class TestIncidentBodyAndTitle:
    """Tests for incident body and title formatting."""

    def test_title_includes_component_name(self, client, mock_statuspage):
        """Incident title includes component name."""
        mock_statuspage.find_incident_for_component.return_value = None
        mock_statuspage.create_incident.return_value = {"id": "new-incident"}

        alerts = [make_alert(component_name="My Service")]
        payload = make_webhook_payload(status="firing", alerts=alerts)

        client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        call_kwargs = mock_statuspage.create_incident.call_args.kwargs
        assert "My Service" in call_kwargs["title"]

    def test_body_includes_summary(self, client, mock_statuspage):
        """Incident body includes alert summary."""
        mock_statuspage.find_incident_for_component.return_value = None
        mock_statuspage.create_incident.return_value = {"id": "new-incident"}

        alerts = [make_alert(summary="Database connection timeout")]
        payload = make_webhook_payload(status="firing", alerts=alerts)

        client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        call_kwargs = mock_statuspage.create_incident.call_args.kwargs
        assert "Database connection timeout" in call_kwargs["body"]

    def test_body_includes_multiple_summaries(self, client, mock_statuspage):
        """Incident body includes all alert summaries."""
        mock_statuspage.find_incident_for_component.return_value = None
        mock_statuspage.create_incident.return_value = {"id": "new-incident"}

        alerts = [
            make_alert(summary="First issue"),
            make_alert(summary="Second issue"),
        ]
        payload = make_webhook_payload(status="firing", alerts=alerts)

        client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        call_kwargs = mock_statuspage.create_incident.call_args.kwargs
        assert "First issue" in call_kwargs["body"]
        assert "Second issue" in call_kwargs["body"]


class TestRaceConditionHandling:
    """Tests for race condition handling during incident creation."""

    def test_create_fails_but_incident_exists_updates_instead(self, client, mock_statuspage):
        """If create fails but incident now exists, update it (race condition)."""
        # First find returns None (no incident)
        # Create fails
        # Second find returns an incident (created by concurrent request)
        mock_statuspage.find_incident_for_component.side_effect = [
            None,  # First check: no incident
            {"id": "race-created-incident"},  # Re-check after create fails
        ]
        mock_statuspage.create_incident.side_effect = Exception("Conflict")
        mock_statuspage.update_incident.return_value = {"id": "race-created-incident"}

        payload = make_webhook_payload(status="firing")
        response = client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200
        # Should have attempted create, then fallen back to update
        mock_statuspage.create_incident.assert_called_once()
        mock_statuspage.update_incident.assert_called_once()
        assert mock_statuspage.update_incident.call_args.kwargs["incident_id"] == "race-created-incident"

    def test_create_fails_no_incident_exists_propagates_error(self, client, mock_statuspage):
        """If create fails and no incident exists, propagate the error."""
        # Both finds return None - not a race condition, real error
        mock_statuspage.find_incident_for_component.return_value = None
        mock_statuspage.create_incident.side_effect = Exception("API Error")

        payload = make_webhook_payload(status="firing")
        response = client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 500
        assert b"Internal server error" in response.data
        mock_statuspage.update_incident.assert_not_called()


class TestErrorHandling:
    """Tests for error handling."""

    def test_api_error_returns_500(self, client, mock_statuspage):
        """API errors return 500."""
        mock_statuspage.find_incident_for_component.side_effect = Exception(
            "API Error"
        )

        payload = make_webhook_payload(status="firing")
        response = client.post(
            "/alert",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 500
        assert b"Internal server error" in response.data
