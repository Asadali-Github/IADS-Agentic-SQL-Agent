# Observability

> Status: scaffold — content to be added during the hackathon.

Today the system uses `structlog` for structured logs. The production design (see [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)) calls for OpenTelemetry tracing, Prometheus metrics, and Sentry error aggregation.

This directory will hold:

- `otel/` — OpenTelemetry collector config
- `prometheus/` — Prometheus scrape config + alert rules
- `grafana/` — dashboard JSON

(TODO: implement during the hackathon.)
