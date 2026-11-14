# Observability: telemetry, dashboards and alerts

## Signals

- **Logs.** Structured JSON (structlog) on stdout. Every line has `request_id`, and `trace_id` /
  `span_id` when tracing is on. Business events are named, for example `audit` (with the
  action), `retention_applied`, `incidents_escalated`, `sso_sign_in_refused`,
  `ai_provider_error` and `dependency_unavailable`.
- **Health.** `GET /api/v1/health/live` (process) and `GET /api/v1/health/ready` (database and
  Redis, each with latency). Compose and `deploy.sh` gate on readiness. Caddy hides both from the
  internet.
- **Traces.** OpenTelemetry for FastAPI, SQLAlchemy and httpx. Calls to Odoo, Shopify, the IdP
  and model providers appear as child spans.
- **Metrics.** OpenTelemetry counters:

  | Metric | Attributes | Meaning |
  |---|---|---|
  | `operon.integration.syncs` | `outcome`, `kind` | Sync results; `kind` is the error class on failure |
  | `operon.insights.raised` | `rule`, `severity` | New insights from detectors |
  | `operon.workflows.finished` | `status`, `target` | Purchase requests completed or failed |
  | `operon.agent.runs` | `kind`, `status` | Assistant and agent runs |
  | `operon.model.tokens` | `kind`, `provider` | Model spend (input + output) |

  The database also holds per-organisation history: sync jobs, detection runs, workflow events
  and run steps. The UI shows it, which is the place to investigate a single tenant.

## Turning it on

```bash
OPERON_OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.internal:4318   # OTLP/HTTP
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production
```

The service name comes from `OPERON_SERVICE_NAME`: `operon-api` by default, and
`operon-worker` for the worker in `compose.production.yml`. Any OTLP backend
works.

## Dashboards

1. **Service:** request rate, error rate (5xx), p50/p95 latency by route, and readiness latency
   for the database and Redis.
2. **Integrations:** sync outcomes per minute, the failure ratio by `kind`, and how stale the
   last successful sync is.
3. **Intelligence and workflows:** insights raised by rule and severity, and workflows finished
   by status.
4. **AI:** runs by status, tokens per hour, and limited or refused runs.

## Alerts

| Alert | Condition | Severity | First step |
|---|---|---|---|
| API unavailable | readiness failing > 2 min | Page | Check the database and Redis; `deploy.sh` rollback if it followed a deploy |
| Error rate | 5xx > 2% of requests for 10 min | Page | Find the route and trace; correlate with the last deploy |
| Latency | p95 > 1.5 s for 15 min | Ticket | Look at the slowest SQL spans; compare against the load-test baseline |
| Sync failures | failed / all syncs > 20% for 30 min, or one connection failing 3× | Ticket | Connection page → last error; credentials or the remote system |
| Workflow failures | any `operon.workflows.finished{status="failed"}` | Ticket | Execution history; retry from the UI once the cause is fixed |
| Stale agent runs | runs marked failed by `fail_stale_runs` | Ticket | Worker restarts or model timeouts |
| Token spend | tokens/hour > 3× the 7-day average | Ticket | Which organisation; usage limits and budgets cap it |
| Backups | no successful backup in 26 h, or a failed drill | Page | Backup job logs; storage credentials |
| Certificate | TLS certificate expires in < 14 days | Ticket | Caddy logs (automatic renewal failed) |
