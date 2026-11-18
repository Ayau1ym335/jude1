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

- `governance`: `user`, `session`, `role_grant` (IAM), `rejection`, `report`, `template*`, `frame_definition`
- `clinical.cohort` (conditional)
- `ops.backup_record`, `ops.blob_verification`

Columns such as `created_by` are `uuid NOT NULL` without a foreign key. The IAM migration adds the FKs to `governance.user`.

### Enumerations without a CHECK yet

The full value set of these columns is not in the repository. Each is `text NOT NULL`, and the owning task adds the CHECK:

| Column | Value set lives in | Owning task |
|---|---|---|
| `geometry.scan.status` | — | FN-SCN |
| `geometry.design_version.status` | 07 §8.1 | FN-REV-06 |
| `governance.config_version.state` | — | FN-CFG |
| `geometry.measurement_value.provenance_class` | DATA-13 | — |

## Roles and grants (least privilege, IDR-07)

All four roles are `NOLOGIN` groups. The migration creates no login users and contains no credentials. Each deployment creates its own login users and grants them membership: the API user gets `app_rw` + `audit_append`, the worker user gets `worker_rw`.

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
