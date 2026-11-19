# Log schema `log/1` and logging rules

This document describes how the Jude services log. It covers the API, the worker and the migration tool (XC-FND-11; NFR-08, SEC-18).

- **Machine-readable schema:** [log-schema.json](log-schema.json) (JSON Schema 2020-12). Every log line validates against it; the tests check this.
- **Implementation:** [`jude_platform.logs`](src/jude_platform/logs.py) and [`jude_platform.correlation`](src/jude_platform/correlation.py).

## One line = one JSON object on stdout

```json
{"correlation_id":"ui-action-12345678","duration_ms":4.2,"event":"http.request","level":"info","logger":"jude_api.request","method":"POST","route":"/api/v1/cases/{case_id}/scans","schema":"log/1","service":"api","status":202,"ts":"2026-11-19T10:00:00.123Z","version":"0.0.0"}
```

| Field | Meaning |
|---|---|
| `ts` | UTC timestamp in milliseconds (NFR-08) |
| `service`, `version` | Which program and which build wrote the line. The version comes from `JUDE_BUILD_VERSION` if set (CI sets it), otherwise from the package version (NFR-08). |
| `event` | A static dotted name, e.g. `http.request` or `job.failed`. This is what you search for. |
| `correlation_id` | Follows a user action from the UI through the API and the job to the kernel result (see below). |
| Metadata fields | `method`, `route`, `status`, `duration_ms`, `error_code`, `job_id`, `job_type`, `check`, … The full list is the `FIELDS` table in `logs.py` and in the schema. |
| `exc_type`, `frames` | For an exception: its type, plus `file:line:function` frames. |
| `dropped_fields` | How many unknown or mistyped fields were removed from this line. |

## What can never be in a log

This rule covers personal data (SEC-18), secrets and mesh data. It is enforced in four layers, so a mistake in calling code cannot leak data:

1. **Events, not messages.** `log.info("case %s", x)` writes `log.unstructured` and drops `x`. Arguments are never interpolated.
2. **Allow-listed fields only.** There is no field for request or response bodies, query strings, headers, cookies, file names, clinic references, case contents or arrays. Any other `extra` key is dropped and counted.
3. **Exceptions without messages or locals.** Only the type and the frames are written.
4. **Redaction net.** Every string value is scanned for e-mail addresses, IIN-like 12-digit numbers, phone numbers, bearer tokens and `password=` / `token=` / `session=` pairs.

What else follows from these rules:

- **The API logs the route template, not the path.** It writes `/api/v1/cases/{case_id}`, not the request path or its query string.
- **uvicorn's access log is disabled.** It would print raw paths; `http.request` replaces it.
- **Third-party text is kept only from a short list:** uvicorn server lifecycle and Alembic migration steps, both after redaction. Chatty libraries such as HTTP clients and Alembic plugin setup log warnings only.

The completion test of XC-FND-11 is `services/api/tests/test_api_logging_errors.py::test_seeded_identifiers_never_appear_in_logs`. It sends synthetic identifiers through every request channel: path, query, headers, cookies, body, invalid body and exception text. None of them may appear in the logs.

## Correlation ID

| Step | What happens |
|---|---|
| UI | Sends `X-Correlation-ID` with each action. The generated client of XC-FND-06 adds it. |
| API | Keeps a well-formed incoming ID (`[A-Za-z0-9][A-Za-z0-9-]{7,63}`) or creates one (UUID hex). It returns the ID in the `X-Correlation-ID` header and in every DS-24 error body, and puts it into job payloads with `correlation.inject`. |
| Worker | `job_context` binds the ID from the payload. The job result envelope (`job-result/1`) stores it next to the kernel's OpResult. |
| Kernel | Never sees the ID; it stays pure (IF-03). |

## Probes and metrics (internal only)

`/livez`, `/readyz` and `/metrics` on the API container (port 8000) are outside `/api`, so the proxy never routes them; `scripts/smoke.sh` checks this.

- `/readyz` checks the database, that the schema is at the migration head, and the blob store.
- `/metrics` is Prometheus text: requests by method, route template and status, durations by route, and build info.
