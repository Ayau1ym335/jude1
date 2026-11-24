# Database schema baseline (XC-FND-05)

This document describes the schema created by migration `0001_baseline` ([0001_baseline.py](src/jude_api/migrations/versions/0001_baseline.py)). Read it before you add a migration in a later task.

- **Sources:** DATA_STRUCTURES_AND_INTERFACES_v1.0 §1 (DS-04…DS-25) and §3.1 (zones); FN-AUD-06, FN-CAS-01, FN-JOB-01; IDR-02, IDR-03, IDR-06, IDR-07.
- **Engineering-lead decisions of 2026-11-18:**
  - `artifact` lives in its own schema, `data`, as DS-19 and TECHNICAL_DESIGN specify. There are therefore six schemas, not the five the WBS mentions.
  - Every table whose columns are specified in the DS set is created here.

## Running migrations

| Command | What it does |
|---|---|
| `jude-migrate upgrade` | Applies migrations up to head. Reads `JUDE_DATABASE_URL`. The `migrate` compose service runs it before api and worker start. |
| `jude-migrate sql` / `just migrate-sql` | Prints the SQL without running it, for review before applying to Supabase. |
| `just test-int` | Starts a throwaway Postgres, migrates fresh empty databases and runs the integration tests (`pytest -m integration`). CI runs the same tests in `.github/workflows/db.yml`. |

Migrations are **forward-only**: `downgrade()` raises, and a fix is a new migration. Migrations are hand-written SQL, with no ORM autogenerate. They ship inside the `jude_api` package (`src/jude_api/migrations/`) so the API image can apply them.

## Schemas and tables

| Schema | Zone | Tables |
|---|---|---|
| `clinical` | Z-CLIN | `"case"` (quoted: `case` is a keyword), `consent_ref`, `prescription`, `scan_metadata` |
| `geometry` | Z-GEO | `scan`, `landmark_set`, `landmark`, `landmark_history`, `frame`, `measurement_set`, `measurement_value`, `design`, `design_version`, `operation`, `validity_report` |
| `governance` | Z-GOV | `config_version`, `measurement_definition`, `approval`, `export` |
| `data` | Z-GEO (blob refs) | `artifact` |
| `audit` | Z-AUD | `audit_event` (hashed core), `audit_summary` (erasable), `chain_head` |
| `ops` | Z-OPS | `job`, `idempotency_key` |

### Tables left to the tasks that own them

These tables have no column specification yet, so the owning task's migration creates them:

- `governance`: `role_grant` (IAM), `rejection`, `report`, `template*`, `frame_definition`. (`user`, `login_failure` and `session` came with `0003_iam_accounts`.)
- `clinical.cohort` (conditional)
- `ops.backup_record`, `ops.blob_verification`

### Actor references (`0005_user_references`, TSK-IAM-05-B)

Every actor column references `governance."user"(id)`. That covers each `uuid` column named `*_by`, plus `ops.job.requested_by` and `ops.idempotency_key.user_id` (22 foreign keys). Two rules make this safe:
- accounts are never deleted, only deactivated (SEC-19);
- `app_rw` has no DELETE on `governance."user"`.

`audit.audit_event.user_id` has **no** foreign key:
- the audit record's integrity rests on its hash chain alone;
- it also records actors that are not accounts (`user_id` NULL, role `system`).

Test fixtures that insert rows must create the account first. The integration conftest offers `seed_user` for this.

### Design version states (`0007_design_version_states`, TSK-REV-06-A)

`jude_api.domain.rev.states` is the single authority for status changes (FN-REV-06). The database is the backstop:
- **CHECK** over the eight statuses: `draft`, `saved`, `reviewed_pass`, `reviewed_fail`, `approved`, `rejected`, `exported`, `superseded`.
- **Trigger `geometry.design_version_guard`:**
  - a version is inserted as `draft` only;
  - a status change must be an allowed pair (the same pairs as the Python table; a unit test compares them);
  - outside `draft`, every column except `status` is frozen (INV-03).
- **CHECK** that a version outside `draft` and `superseded` has `params_sha` and `geometry_sha`.
- **One open draft per design** (partial unique index). An edit of a non-draft creates draft n+1 with parent n (FR-091).

Violations raise SQLSTATE `P0001` with the prefix `ILLEGAL_STATE`.

### Idempotency replay (`0006_idempotency_replay`, TSK-API-01-A)

`ops.idempotency_key` gains two columns:
- `request_sha`: SHA-256 of method, path and body. The same key with another request is refused.
- `body_bytes`: the exact response bytes, so a replay is byte-identical. jsonb reorders keys and cannot guarantee that.

A CHECK ties `body_sha` to `sha256(body_bytes)`. `body` keeps the parsed JSON for queries. The rows have no expiry yet; a clean-up job (app_rw has DELETE) can follow when retention is decided.

### Enumerations without a CHECK yet

The full value set of these columns is not in the repository. Each is `text NOT NULL`, and the owning task adds the CHECK:

| Column | Value set lives in | Owning task |
|---|---|---|
| `geometry.scan.status` | — | FN-SCN |
| `governance.config_version.state` | — | FN-CFG |
| `geometry.measurement_value.provenance_class` | DATA-13 | — |

## Roles and grants (least privilege, IDR-07)

All four roles are `NOLOGIN` groups. The migration creates no login users and contains no credentials. Each deployment creates its own login users and grants them membership: the API user gets `app_rw` + `audit_append`, the worker user gets `worker_rw`.

The API works as `app_rw`. The audit service (`jude_api.platform.aud`, FN-AUD-01) switches to `audit_append` only for the append itself:
- it takes a transaction advisory lock, which serialises appends;
- it runs `SET LOCAL ROLE audit_append` and calls `audit.append_event`;
- it switches back to `app_rw`.

Everything happens in the caller's transaction, so a rollback removes the event. Migration `0002_audit_ui_session` adds `audit_event.ui_session_id` (DATA-19, outside the hashed core) and the trailing `p_ui_session_id` parameter of `append_event`.

| Role | clinical, geometry, governance, data, ops | audit |
|---|---|---|
| `app_rw` | SELECT, INSERT, UPDATE. DELETE only on `geometry.operation`, `geometry.landmark` and `ops.idempotency_key`. No UPDATE on the immutable tables: `data.artifact`, `geometry.landmark_history`, `geometry.measurement_value`, `geometry.validity_report`, `governance.measurement_definition`. | none |
| `worker_rw` | `ops.job` SELECT, UPDATE only | none |
| `audit_append` | none | SELECT, INSERT on `audit_event` and `audit_summary`; SELECT on `chain_head`; EXECUTE on `audit.append_event` |
| `admin_ro` | SELECT | SELECT |

`PUBLIC` gets nothing: no schema usage and no EXECUTE on the audit functions. No role has TRUNCATE.

## Audit chain (FN-AUD-06, IDR-06, ALG-58)

- **`audit.append_event(...)`** is a `SECURITY DEFINER` function with `search_path` pinned. It does five things:
  1. Locks `chain_head`.
  2. Requires `seq = last_seq + 1` and `prev_hash = last_hash`; otherwise it raises `40001`.
  3. Inserts the core row.
  4. Inserts the summary row, if one is given.
  5. Moves the chain head.
- **Hash computation stays with the caller.** IF-08 / FN-AUD-01 computes `hash = SHA-256(prev_hash ‖ JCS(core))`; the database stores it and enforces continuity.
- **The core rows of `audit_event` cannot be changed by any role.** A trigger refuses UPDATE, DELETE and TRUNCATE with SQLSTATE `P0001`; for non-owner roles the missing grants fail first with `42501`.
- **`audit_summary` is the erasable part.** Erasure uses the privileged purge credential of FN-CAS-08, which this migration does not create.
- **CI check (TSK-AUD-06-C, CI-FN-AUD-06):** [`tools/contract/audit_immutability.py`](../../tools/contract/audit_immutability.py) keeps these rules from regressing.
  - Contract stage: no `/audit*` path offers PUT, PATCH or DELETE, in `openapi.json` or in the live routes; POST only for `/api/v1/audit/verify` (FN-AUD-03, appends only). Mutate requests to the audit paths answer 403/404/405. Shipped code outside `migrations/` holds no SQL that updates, deletes, truncates, alters or re-grants an `audit.*` table.
  - Integration stage ([test_audit_immutability_db.py](tests/integration/test_audit_immutability_db.py)): no application role, no API login and not PUBLIC has UPDATE, DELETE, TRUNCATE or column UPDATE on an `audit` table or owns one; the BEFORE UPDATE/DELETE/TRUNCATE triggers are enabled; `append_event` is the only SECURITY DEFINER function, with a pinned `search_path` and EXECUTE for `audit_append` alone.
  - A later migration that breaks one of these fails CI. Against a deployed database: `python tools/contract/audit_immutability.py --db-url URL --app-login <api login>`.

## Invariants enforced in the database

| Rule | How it is enforced |
|---|---|
| Case ID format `J-` + 8 Crockford base32 characters (FN-CAS-01) | CHECK. No identity columns exist (DATA-10); a test checks this. |
| SHA-256 columns | `char(64)` with a lowercase-hex CHECK |
| Frame is rigid with no reflection (DS-06, INV-06) | `|det − 1| ≤ 1e-9`; the stored `det` must equal the determinant computed from `matrix` (`geometry.rotation_det`); bottom row exactly `0 0 0 1`; 16 finite values |
| Approval binds the version's geometry hash (INV-04) | Composite FK `(design_version_id, geometry_sha)` → `design_version(id, geometry_sha)` |
| An approval has a prescription (FR-182) | `prescription_sha NOT NULL` |
| Export released ⇒ re-import passed and STL + manifest hashes present (FR-102/103) | CHECK |
| Artifact | kind and bucket from DS-19; `prescription_file` ⇔ bucket `prescriptions`; one row per (case, sha) (INV-01) |
| Measurement value has a definition id + version (INV-05) | FK to `governance.measurement_definition` |
| No severity, threshold or grade fields (FR-045) | No such columns exist; a test checks this |
| Measurement value is computed or carries a reason | `value` or `not_computed_reason`, exactly one |
| Job type and status (IF-02, DS-17) | Type is versioned (`regenerate.v1`); status from DS-17; `running` needs lease + worker; terminal ⇔ `finished_at`; `failed` needs `error_code`. Partial indexes for claim and reaper. |
| Configuration | At most one `active` version |
| Formula and rules (IDR-02/03) | `formula_type`, `contour_selection_rule`, `diagonal_centre_rule`, `angle_reference_axis` checked against their sets |

The migration defaults no clinical, threshold or production value (DEC-029). The only defaults are timestamps, generated IDs, `attempts = 0`, `regen_failed = false`, `reapproval_required = false` and an empty `parent_shas`.
