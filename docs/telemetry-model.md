# Telemetry model

RecallRoot treats OpenTelemetry as a causal evidence model, not as decorative
request monitoring. Every project-specific field uses the `recallgraph.*`
namespace; standard resource and HTTP attributes remain standard when present.

## Export path

The Python SDK sends OTLP/HTTP to `http://localhost:4318`:

- `/v1/traces`
- `/v1/logs`
- `/v1/metrics`

SigNoz’s Foundry-generated ingester stores all three signals. The API uses
service name `recallroot-api` and deployment environment
`development` by default. Metric export is periodic, so the direct verifier
allows bounded eventual-consistency retries.

The ingester obtains its active pipelines from SigNoz over OpAMP. RecallRoot's
casting pins that manager endpoint to the generated SigNoz service on `:4320`;
this works around Foundry `v0.2.16` resolving the MCP container instead when MCP
is enabled. A healthy HTTP endpoint alone does not prove ingestion, so the
strict verifier still queries stored traces, logs, and metrics directly.

## Trace topology

### Session A: provenance creation

```text
POST /demo/ingest-unsafe-memory
└── ingest_source
    └── recallgraph.memory.write
```

The write span’s 32-character trace ID, 16-character span ID, and trace flags
are persisted on the memory record before Session A completes.

### Session B: unsafe decision

```text
POST /agent/refund
└── invoke_agent support-refund-agent
    ├── parse_request
    ├── recallgraph.memory.use ── Link ──▶ Session A memory.write
    ├── agent.decision
    ├── execute_tool issue_refund
    └── recallgraph.outcome.evaluate
```

The memory-use link is an actual `opentelemetry.trace.Link` created from the
persisted remote span context. It is not simulated by an application edge.

### Remediation and replay

```text
POST /memories/{id}/quarantine
└── recallgraph.memory.quarantine

POST /incidents/{id}/replay
└── recallgraph.replay
    └── invoke_agent support-refund-agent
        ├── recallgraph.memory.use
        ├── agent.decision
        ├── execute_tool request_manager_approval
        └── recallgraph.outcome.evaluate
```

The replay records original and repaired trace IDs in its response and evidence.

## Attribute contract

### Common

| Attribute | Meaning | Cardinality |
|---|---|---|
| `recallgraph.session.id` | One synthetic agent session | High; traces only |
| `recallgraph.agent.run_id` | One agent invocation | High; traces only |
| `recallgraph.scenario` | Stable scenario name | Bounded |

### Memory

| Attribute | Example |
|---|---|
| `recallgraph.memory.id` | `mem_unsafe_refund_policy` |
| `recallgraph.memory.operation` | `write`, `use`, `quarantine` |
| `recallgraph.memory.status` | `active`, `quarantined` |
| `recallgraph.memory.source.type` | `external_document` |
| `recallgraph.memory.source.trust` | `untrusted` |
| `recallgraph.memory.source.name` | `unverified-refund-playbook.txt` |
| `recallgraph.memory.age_seconds` | Numeric age at retrieval |
| `recallgraph.memory.origin.trace_id` | Session A trace bridge |
| `recallgraph.memory.origin.span_id` | Session A span bridge |
| `recallgraph.memory.retrieval_rank` | Deterministic retrieval rank |
| `recallgraph.memory.content_hash` | SHA-256 evidence without raw content |
| `recallgraph.memory.sanitized_preview` | Short presentation-safe preview |

### Action and policy

| Attribute | Example |
|---|---|
| `recallgraph.action.id` | Synthetic action ID |
| `recallgraph.action.type` | `issue_refund` |
| `recallgraph.action.sensitivity` | `high` |
| `recallgraph.action.amount_bucket` | `10000-50000` |
| `recallgraph.approval.required` | `true` |
| `recallgraph.approval.present` | `false` |
| `recallgraph.policy.outcome` | `violation` or `pass` |

### Risk and remediation

| Attribute | Example |
|---|---|
| `recallgraph.risk.score` | `90` |
| `recallgraph.risk.level` | `critical` |
| `recallgraph.replay.original_trace_id` | Trace being replayed |
| `recallgraph.replay.result` | `improved` |
| `recallgraph.remediation.type` | `memory_quarantine` |

Origin IDs are intentionally both a real span link and searchable attributes.
The duplication is a compatibility bridge for evidence clients that do not yet
return span-link objects.

## Structured events

The event logger emits JSON and an OpenTelemetry log record while a span is
current. `trace_id` and `span_id` are present on every correlated event.

| Event | Trigger |
|---|---|
| `memory_written` | Durable memory and provenance committed |
| `memory_retrieved` | Active memory selected |
| `memory_influenced_decision` | Operative instruction affected choice |
| `sensitive_action_selected` | Refund/approval tool chosen |
| `policy_violation_detected` | Independent trusted policy failed |
| `memory_quarantined` | Memory disabled |
| `request_replayed` | Original request executed again |
| `replay_improved_outcome` | Repaired run changed violation to pass |

Example semantic body:

```json
{
  "event": "policy_violation_detected",
  "action_type": "issue_refund",
  "amount_bucket": "10000-50000",
  "memory_source_trust": "untrusted",
  "approval_required": true,
  "approval_present": false
}
```

No real names, email addresses, full prompts, or payment details belong in an
event body.

## Metrics

| Instrument | Type | Bounded labels |
|---|---|---|
| `recallgraph.memory.uses` | Counter | `trust`, `status` |
| `recallgraph.policy.violations` | Counter | `action_type`, `source_trust` |
| `recallgraph.sensitive.actions` | Counter | `outcome` |
| `recallgraph.memory.risk.score` | Histogram | `trust` |
| `recallgraph.replays` | Counter | `result` |
| `recallgraph.investigation.duration` | Histogram | `result` |
| `recallgraph.causal_chain.depth` | Histogram | `scenario` |

Never add memory IDs, action IDs, trace IDs, session IDs, customer IDs, or user
IDs as metric labels. Those values are useful on spans but would create
unbounded metric time series.

Expected complete-demo observations include at least one policy violation and
one replay with `result=improved`. A replay does not decrement a monotonic
violation counter; the repaired run instead emits a `pass` sensitive-action
outcome and no additional violation.

Counters use OTLP delta temporality. SigNoz therefore aggregates them with
`sum`, including the first increment emitted by a newly started API process.
This avoids treating that first policy violation as the baseline of a
cumulative series and missing the alert.

## Transparent risk score

Risk is a bounded heuristic:

| Factor | Points |
|---|---:|
| Untrusted source | +35 |
| Expired/stale memory | +20 |
| Sensitive action influenced | +20 |
| Required approval missing | +15 |
| Repeated retrieval | up to +10 |
| Maximum | 100 |

Levels are Low `0–29`, Medium `30–59`, High `60–79`, and Critical `80–100`.
The API and UI return the contributing factors; no model generates the number.

## Query Builder investigation

The application investigator uses the SigNoz MCP endpoint first. It searches
for the action span, retrieves the complete action trace, follows the memory
origin identifiers, and retrieves the origin trace. Direct Query Builder REST
calls are the secondary path when MCP is unavailable; persisted local evidence
is the final, visibly labelled fallback. Every path applies the same required
span checks before producing the deterministic explanation.

Useful trace filters in SigNoz:

```text
recallgraph.action.id = '<action-id>'

recallgraph.memory.id = 'mem_unsafe_refund_policy'
AND recallgraph.memory.operation = 'write'

name = 'recallgraph.memory.use'
AND recallgraph.memory.origin.trace_id EXISTS
```

The graph builder uses these identifiers to obtain the full action and origin
traces. Every evidence item exposes a direct SigNoz trace URL.

The dashboard asset uses Query Builder v5 with `sum` for delta counters and
p50/p95 for the risk histogram. The alert uses a five-minute rolling window,
one-minute frequency, and fires when the summed violation count is above zero.

## Verification contract

`scripts/verify_telemetry.py` checks application graph/replay invariants and,
when a SigNoz key is available, queries `/api/v5/query_range` directly for:

1. memory-write, memory-use, outcome-evaluation, and replay spans on the exact
   origin, action, and replay trace IDs of the current incident;
2. current-run origin trace/span attributes on the memory-use span;
3. a `policy_violation_detected` log correlated to the current action trace;
4. a positive policy-violation counter sum after the current incident time;
5. a positive improved-replay counter sum after the current resolution time.

Strict mode additionally requires the causal graph to report `source=signoz`,
the investigation to report `source=signoz_mcp`, and the named alert rule's
`/api/v2/rules/{id}/history/timeline` response to contain a firing transition
after the current incident's `detected_at`. The alert-history poll allows four
minutes for the one-minute evaluator and SigNoz's delayed evaluation window.

Use `make verify-signoz` for the strict mode. Missing evidence is a failure, not
silently converted to a passing local check.
