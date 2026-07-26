# SigNoz assets

`recallroot-dashboard.json` is a SigNoz v5 dashboard export with five Query
Builder panels. Import it in **Dashboards → New dashboard → Import JSON**, or
run `make signoz-dashboard` after setting `SIGNOZ_API_KEY`.

RecallRoot exports monotonic counters with OTLP delta temporality. Query Builder
uses `sum` where the alert needs the raw delta and `increase` for outcome charts.
The transparent risk score is a gauge, so the dashboard can compare the latest
trusted and untrusted decision scores directly.

`alert-rule.template.json` is a current `/api/v2/rules` threshold-rule payload.
SigNoz requires alert rules to reference a notification channel that already
exists. The provisioning script validates `SIGNOZ_ALERT_CHANNEL` against
`GET /api/v1/channels` and substitutes it for
`__SIGNOZ_ALERT_CHANNEL__`; the checked-in template is never mutated.

Use:

```bash
cp .env.example .env
# Set SIGNOZ_API_KEY and the exact existing SIGNOZ_ALERT_CHANNEL in .env.
make signoz-provision
```

The script reconciles resources by title: it creates missing resources and
updates existing dashboard and alert definitions from the checked-in assets.
It does not create a notification destination, because doing so would require
real external credentials and an explicit delivery choice.

For a self-contained local demo, create a **Webhook** channel in the SigNoz UI
with URL
`http://host.docker.internal:8000/integrations/signoz-alerts`, give it a stable
name such as `RecallRoot Local Sink`, and put that exact name in
`SIGNOZ_ALERT_CHANNEL`. The endpoint returns `202 Accepted`, emits the bounded
`signoz_alert_received` structured event, and never forwards the payload.

## Foundry compatibility patch

`casting.yaml` deliberately patches the generated ingester
`server_endpoint` to
`ws://recallroot-signoz-signoz-0:4320/v1/opamp`. In Foundry `v0.2.16`, enabling
MCP can make the default address resolver choose
`recallroot-signoz-mcp:4320`; the collector then loads no-op pipelines because
MCP is not the OpAMP manager. Keep the correction in the source casting and
regenerate with `make signoz-lock`. Never patch the ignored file under `pours/`
directly.
