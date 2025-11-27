# Statuspage Bridge

A lightweight Python service that bridges Prometheus Alertmanager webhooks to Atlassian Statuspage incidents.

> **Attribution**: This project is inspired by [nathandeamer/prometheus-alerts-to-statuspage](https://github.com/NathanDeamer/prometheus-alerts-to-statuspage) and the accompanying [blog post](https://nathandeamer.medium.com/automating-atlassian-statuspage-with-prometheus-alertmanager-d3270ed7a10a).

## How It Works

1. Prometheus fires alerts with Statuspage labels/annotations
2. Alertmanager groups alerts and sends webhooks to this service
3. This service creates/updates/resolves incidents on Statuspage

## Setup

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `STATUSPAGE_API_KEY` | Yes | Statuspage API key |
| `LOG_LEVEL` | No | Logging level (default: INFO) |

### Docker Compose

```yaml
statuspage-bridge:
  build: ./statuspage-bridge
  environment:
    - STATUSPAGE_API_KEY=${STATUSPAGE_API_KEY}
  networks:
    - monitoring
```

### Alertmanager Configuration

```yaml
route:
  routes:
    - match:
        statuspage: "true"
      receiver: statuspage-webhook
      group_by: [statuspagePageId, statuspageComponentId]
      group_wait: 30s
      group_interval: 1m
      continue: true

receivers:
  - name: statuspage-webhook
    webhook_configs:
      - url: 'http://statuspage-bridge:8080/alert'
        send_resolved: true
```

### Prometheus Alert Rules

```yaml
groups:
  - name: statuspage-alerts
    rules:
      - alert: ServiceDown
        expr: probe_success == 0
        for: 2m
        labels:
          statuspage: "true"
          statuspagePageId: "your-page-id"
          statuspageComponentId: "your-component-id"
        annotations:
          statuspageComponentName: "My Service"
          statuspageImpactOverride: "major"
          statuspageComponentStatus: "partial_outage"
          statuspageSummary: "Service is experiencing issues"
```

### Alert Labels & Annotations

**Labels** (used for routing and grouping):
- `statuspage: "true"` - Routes alert to Statuspage webhook
- `statuspagePageId` - Your Statuspage page ID
- `statuspageComponentId` - Component ID to update

**Annotations** (used for incident details):
- `statuspageComponentName` - Component name for incident title
- `statuspageImpactOverride` - Impact level: `none`, `minor`, `major`, `critical`
- `statuspageComponentStatus` - Component status: `operational`, `degraded_performance`, `partial_outage`, `major_outage`
- `statuspageSummary` - Description text for the incident

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## License

MIT
