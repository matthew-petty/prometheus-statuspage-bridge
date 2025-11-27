"""Statuspage API client."""

import logging
from typing import Any

import requests
from requests import Response
from requests.exceptions import HTTPError

logger = logging.getLogger(__name__)


class StatuspageClient:
    """Client for the Statuspage.io API."""

    DEFAULT_TIMEOUT = 10  # seconds

    def __init__(self, api_key: str, timeout: int | None = None):
        self.api_key = api_key
        self.base_url = "https://api.statuspage.io/v1"
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"OAuth {api_key}",
            "Content-Type": "application/json",
        })

    def _check_response(self, response: Response, operation: str) -> None:
        """Check response and log details on error."""
        try:
            response.raise_for_status()
        except HTTPError:
            logger.error(
                f"Statuspage API error during {operation}: "
                f"status={response.status_code}, body={response.text}"
            )
            raise

    def get_unresolved_incidents(self, page_id: str) -> list[dict[str, Any]]:
        """Fetch all unresolved incidents for a page."""
        url = f"{self.base_url}/pages/{page_id}/incidents/unresolved.json"
        response = self.session.get(url, timeout=self.timeout)
        self._check_response(response, "get_unresolved_incidents")
        return response.json()

    def find_incident_for_component(
        self, page_id: str, component_id: str
    ) -> dict[str, Any] | None:
        """Find an open incident affecting a specific component."""
        incidents = self.get_unresolved_incidents(page_id)
        for incident in incidents:
            components = incident.get("components", [])
            for component in components:
                if component.get("id") == component_id:
                    return incident
        return None

    def create_incident(
        self,
        page_id: str,
        component_id: str,
        title: str,
        body: str,
        status: str,
        impact_override: str,
        component_status: str,
    ) -> dict[str, Any]:
        """Create a new incident."""
        url = f"{self.base_url}/pages/{page_id}/incidents.json"
        payload = {
            "incident": {
                "name": title,
                "body": body,
                "status": status,
                "impact_override": impact_override,
                "component_ids": [component_id],
                "components": {
                    component_id: component_status,
                },
            }
        }
        logger.info(f"Creating incident: {title}")
        response = self.session.post(url, json=payload, timeout=self.timeout)
        self._check_response(response, "create_incident")
        return response.json()

    def update_incident(
        self,
        page_id: str,
        incident_id: str,
        component_id: str,
        body: str,
        status: str,
        impact_override: str,
        component_status: str,
    ) -> dict[str, Any]:
        """Update an existing incident."""
        url = f"{self.base_url}/pages/{page_id}/incidents/{incident_id}.json"
        payload = {
            "incident": {
                "body": body,
                "status": status,
                "impact_override": impact_override,
                "components": {
                    component_id: component_status,
                },
            }
        }
        logger.info(f"Updating incident {incident_id}")
        response = self.session.patch(url, json=payload, timeout=self.timeout)
        self._check_response(response, "update_incident")
        return response.json()

    def resolve_incident(
        self,
        page_id: str,
        incident_id: str,
        component_id: str,
        body: str = "",
    ) -> dict[str, Any]:
        """Resolve an incident and set component to operational."""
        url = f"{self.base_url}/pages/{page_id}/incidents/{incident_id}.json"
        payload = {
            "incident": {
                "status": "resolved",
                "body": body or "All alerts have been resolved.",
                "components": {
                    component_id: "operational",
                },
            }
        }
        logger.info(f"Resolving incident {incident_id}")
        response = self.session.patch(url, json=payload, timeout=self.timeout)
        self._check_response(response, "resolve_incident")
        return response.json()
