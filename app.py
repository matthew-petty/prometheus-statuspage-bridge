"""Flask webhook handler for Alertmanager to Statuspage bridge."""

import logging
import os
from typing import Any

from flask import Flask, request, jsonify

from alert import calculate_severity, build_summary, get_component_name
from statuspage import StatuspageClient

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration from environment
API_KEY = os.environ.get("STATUSPAGE_API_KEY", "")
TITLE_TEMPLATE = os.environ.get(
    "INCIDENT_TITLE_TEMPLATE", "{component_name} - Incident"
)
BODY_TEMPLATE = os.environ.get("INCIDENT_BODY_TEMPLATE", "{summary}")

# Validate required configuration at startup
if not API_KEY:
    logger.warning(
        "STATUSPAGE_API_KEY not set - service will fail on webhook requests"
    )

app = Flask(__name__)


def get_client() -> StatuspageClient:
    """Get Statuspage client instance."""
    if not API_KEY:
        raise ValueError("STATUSPAGE_API_KEY environment variable is required")
    return StatuspageClient(API_KEY)


def format_title(component_name: str) -> str:
    """Format incident title using template."""
    return TITLE_TEMPLATE.format(component_name=component_name)


def format_body(summary: str, component_name: str) -> str:
    """Format incident body using template."""
    return BODY_TEMPLATE.format(summary=summary, component_name=component_name)


@app.route("/health", methods=["GET"])
def health() -> tuple[str, int]:
    """Health check endpoint."""
    return "OK", 200


@app.route("/alert", methods=["POST"])
def handle_alert() -> tuple[Any, int]:
    """Handle Alertmanager webhook."""
    payload = request.get_json()
    if not payload:
        logger.warning("Received empty payload")
        return jsonify({"error": "Empty payload"}), 400

    logger.debug(f"Received webhook: {payload}")

    try:
        # Extract group labels
        group_labels = payload.get("groupLabels", {})
        page_id = group_labels.get("statuspagePageId")
        component_id = group_labels.get("statuspageComponentId")

        if not page_id or not component_id:
            logger.warning("Missing statuspagePageId or statuspageComponentId")
            return jsonify({"error": "Missing required group labels"}), 400

        alerts = payload.get("alerts", [])
        status = payload.get("status", "")

        client = get_client()

        # Find existing incident for this component
        existing_incident = client.find_incident_for_component(page_id, component_id)

        if status == "resolved":
            # All alerts resolved - resolve incident
            if existing_incident:
                client.resolve_incident(
                    page_id=page_id,
                    incident_id=existing_incident["id"],
                    component_id=component_id,
                )
                logger.info(f"Resolved incident {existing_incident['id']}")
            else:
                logger.info("No open incident to resolve")
            return "", 200

        # Calculate severity from alerts
        severity = calculate_severity(alerts)
        component_name = get_component_name(alerts)
        summary = build_summary(alerts)

        title = format_title(component_name)
        body = format_body(summary, component_name)

        if existing_incident:
            # Update existing incident
            client.update_incident(
                page_id=page_id,
                incident_id=existing_incident["id"],
                component_id=component_id,
                body=body,
                status=severity["status"],
                impact_override=severity["impact_override"],
                component_status=severity["component_status"],
            )
            logger.info(f"Updated incident {existing_incident['id']}")
        else:
            # Create new incident (with race condition handling)
            try:
                result = client.create_incident(
                    page_id=page_id,
                    component_id=component_id,
                    title=title,
                    body=body,
                    status=severity["status"],
                    impact_override=severity["impact_override"],
                    component_status=severity["component_status"],
                )
                logger.info(f"Created incident {result.get('id')}")
            except Exception as create_error:
                # Race condition: another request may have created an incident
                # Re-check and update if one exists now
                logger.warning(f"Create failed, checking for race condition: {create_error}")
                existing = client.find_incident_for_component(page_id, component_id)
                if existing:
                    logger.info(f"Found existing incident {existing['id']}, updating instead")
                    client.update_incident(
                        page_id=page_id,
                        incident_id=existing["id"],
                        component_id=component_id,
                        body=body,
                        status=severity["status"],
                        impact_override=severity["impact_override"],
                        component_status=severity["component_status"],
                    )
                else:
                    # Not a race condition, re-raise original error
                    raise create_error

        return "", 200

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return jsonify({"error": "Configuration error"}), 500
    except Exception as e:
        logger.error(f"Error processing alert: {e}")
        return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    if not API_KEY:
        raise SystemExit("STATUSPAGE_API_KEY environment variable is required")
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=8080, debug=debug)
