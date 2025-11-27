"""Tests for Statuspage API client."""

import sys
from pathlib import Path

import pytest
import responses
from requests.exceptions import HTTPError

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from statuspage import StatuspageClient


@pytest.fixture
def client():
    """Create a StatuspageClient instance."""
    return StatuspageClient(api_key="test-api-key")


@pytest.fixture
def base_url():
    """Base URL for Statuspage API."""
    return "https://api.statuspage.io/v1"


class TestStatuspageClientInit:
    """Tests for StatuspageClient initialization."""

    def test_sets_api_key(self, client):
        """API key is stored."""
        assert client.api_key == "test-api-key"

    def test_sets_base_url(self, client):
        """Base URL is set correctly."""
        assert client.base_url == "https://api.statuspage.io/v1"

    def test_session_has_auth_header(self, client):
        """Session has OAuth authorization header."""
        assert "Authorization" in client.session.headers
        assert client.session.headers["Authorization"] == "OAuth test-api-key"

    def test_session_has_content_type(self, client):
        """Session has JSON content type header."""
        assert client.session.headers["Content-Type"] == "application/json"


class TestGetUnresolvedIncidents:
    """Tests for get_unresolved_incidents method."""

    @responses.activate
    def test_returns_incident_list(self, client, base_url):
        """Returns list of unresolved incidents."""
        incidents = [
            {"id": "inc-1", "name": "Incident 1", "status": "investigating"},
            {"id": "inc-2", "name": "Incident 2", "status": "identified"},
        ]
        responses.add(
            responses.GET,
            f"{base_url}/pages/page-123/incidents/unresolved.json",
            json=incidents,
            status=200,
        )

        result = client.get_unresolved_incidents("page-123")

        assert len(result) == 2
        assert result[0]["id"] == "inc-1"
        assert result[1]["id"] == "inc-2"

    @responses.activate
    def test_returns_empty_list_when_none(self, client, base_url):
        """Returns empty list when no unresolved incidents."""
        responses.add(
            responses.GET,
            f"{base_url}/pages/page-123/incidents/unresolved.json",
            json=[],
            status=200,
        )

        result = client.get_unresolved_incidents("page-123")

        assert result == []

    @responses.activate
    def test_raises_on_error(self, client, base_url):
        """Raises HTTPError on API error."""
        responses.add(
            responses.GET,
            f"{base_url}/pages/page-123/incidents/unresolved.json",
            json={"error": "Unauthorized"},
            status=401,
        )

        with pytest.raises(HTTPError):
            client.get_unresolved_incidents("page-123")


class TestFindIncidentForComponent:
    """Tests for find_incident_for_component method."""

    @responses.activate
    def test_finds_matching_incident(self, client, base_url):
        """Returns incident when component matches."""
        incidents = [
            {
                "id": "inc-1",
                "name": "Incident 1",
                "components": [{"id": "comp-other", "name": "Other"}],
            },
            {
                "id": "inc-2",
                "name": "Incident 2",
                "components": [{"id": "comp-target", "name": "Target"}],
            },
        ]
        responses.add(
            responses.GET,
            f"{base_url}/pages/page-123/incidents/unresolved.json",
            json=incidents,
            status=200,
        )

        result = client.find_incident_for_component("page-123", "comp-target")

        assert result is not None
        assert result["id"] == "inc-2"

    @responses.activate
    def test_returns_none_when_no_match(self, client, base_url):
        """Returns None when no matching component."""
        incidents = [
            {
                "id": "inc-1",
                "components": [{"id": "comp-other", "name": "Other"}],
            },
        ]
        responses.add(
            responses.GET,
            f"{base_url}/pages/page-123/incidents/unresolved.json",
            json=incidents,
            status=200,
        )

        result = client.find_incident_for_component("page-123", "comp-target")

        assert result is None

    @responses.activate
    def test_returns_none_when_no_incidents(self, client, base_url):
        """Returns None when no unresolved incidents."""
        responses.add(
            responses.GET,
            f"{base_url}/pages/page-123/incidents/unresolved.json",
            json=[],
            status=200,
        )

        result = client.find_incident_for_component("page-123", "comp-target")

        assert result is None

    @responses.activate
    def test_handles_incident_without_components(self, client, base_url):
        """Handles incidents without components field gracefully."""
        incidents = [
            {"id": "inc-1", "name": "No components"},
            {
                "id": "inc-2",
                "components": [{"id": "comp-target", "name": "Target"}],
            },
        ]
        responses.add(
            responses.GET,
            f"{base_url}/pages/page-123/incidents/unresolved.json",
            json=incidents,
            status=200,
        )

        result = client.find_incident_for_component("page-123", "comp-target")

        assert result["id"] == "inc-2"


class TestCreateIncident:
    """Tests for create_incident method."""

    @responses.activate
    def test_creates_incident_with_correct_payload(self, client, base_url):
        """Sends correct payload to create incident."""
        responses.add(
            responses.POST,
            f"{base_url}/pages/page-123/incidents.json",
            json={"id": "new-inc", "name": "Test Incident"},
            status=201,
        )

        result = client.create_incident(
            page_id="page-123",
            component_id="comp-456",
            title="Test Incident",
            body="Test body",
            status="identified",
            impact_override="major",
            component_status="partial_outage",
        )

        assert result["id"] == "new-inc"

        # Verify request payload
        request_body = responses.calls[0].request.body
        import json

        payload = json.loads(request_body)
        assert payload["incident"]["name"] == "Test Incident"
        assert payload["incident"]["body"] == "Test body"
        assert payload["incident"]["status"] == "identified"
        assert payload["incident"]["impact_override"] == "major"
        assert payload["incident"]["component_ids"] == ["comp-456"]
        assert payload["incident"]["components"]["comp-456"] == "partial_outage"

    @responses.activate
    def test_raises_on_error(self, client, base_url):
        """Raises HTTPError on API error."""
        responses.add(
            responses.POST,
            f"{base_url}/pages/page-123/incidents.json",
            json={"error": "Bad Request"},
            status=400,
        )

        with pytest.raises(HTTPError):
            client.create_incident(
                page_id="page-123",
                component_id="comp-456",
                title="Test",
                body="Test",
                status="identified",
                impact_override="major",
                component_status="partial_outage",
            )


class TestUpdateIncident:
    """Tests for update_incident method."""

    @responses.activate
    def test_updates_incident_with_correct_payload(self, client, base_url):
        """Sends correct PATCH payload to update incident."""
        responses.add(
            responses.PATCH,
            f"{base_url}/pages/page-123/incidents/inc-789.json",
            json={"id": "inc-789", "status": "monitoring"},
            status=200,
        )

        result = client.update_incident(
            page_id="page-123",
            incident_id="inc-789",
            component_id="comp-456",
            body="Updated body",
            status="monitoring",
            impact_override="critical",
            component_status="major_outage",
        )

        assert result["id"] == "inc-789"

        # Verify request payload
        import json

        payload = json.loads(responses.calls[0].request.body)
        assert payload["incident"]["body"] == "Updated body"
        assert payload["incident"]["status"] == "monitoring"
        assert payload["incident"]["impact_override"] == "critical"
        assert payload["incident"]["components"]["comp-456"] == "major_outage"


class TestResolveIncident:
    """Tests for resolve_incident method."""

    @responses.activate
    def test_resolves_incident_correctly(self, client, base_url):
        """Sets status to resolved and component to operational."""
        responses.add(
            responses.PATCH,
            f"{base_url}/pages/page-123/incidents/inc-789.json",
            json={"id": "inc-789", "status": "resolved"},
            status=200,
        )

        result = client.resolve_incident(
            page_id="page-123",
            incident_id="inc-789",
            component_id="comp-456",
        )

        assert result["status"] == "resolved"

        # Verify request payload
        import json

        payload = json.loads(responses.calls[0].request.body)
        assert payload["incident"]["status"] == "resolved"
        assert payload["incident"]["components"]["comp-456"] == "operational"

    @responses.activate
    def test_uses_custom_body(self, client, base_url):
        """Uses custom body when provided."""
        responses.add(
            responses.PATCH,
            f"{base_url}/pages/page-123/incidents/inc-789.json",
            json={"id": "inc-789", "status": "resolved"},
            status=200,
        )

        client.resolve_incident(
            page_id="page-123",
            incident_id="inc-789",
            component_id="comp-456",
            body="Custom resolution message",
        )

        import json

        payload = json.loads(responses.calls[0].request.body)
        assert payload["incident"]["body"] == "Custom resolution message"

    @responses.activate
    def test_uses_default_body(self, client, base_url):
        """Uses default body when not provided."""
        responses.add(
            responses.PATCH,
            f"{base_url}/pages/page-123/incidents/inc-789.json",
            json={"id": "inc-789", "status": "resolved"},
            status=200,
        )

        client.resolve_incident(
            page_id="page-123",
            incident_id="inc-789",
            component_id="comp-456",
        )

        import json

        payload = json.loads(responses.calls[0].request.body)
        assert payload["incident"]["body"] == "All alerts have been resolved."
