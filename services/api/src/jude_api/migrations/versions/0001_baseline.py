"""Baseline schema: six zones, roles, grants, CHECK constraints.

Revision ID: 0001_baseline
Revises: -
Create Date: 2026-11-18
Task: XC-FND-05

Sources: DATA_STRUCTURES_AND_INTERFACES_v1.0 §1 (DS-04..DS-25) and §3.1 (zones);
FN-AUD-06 (audit immutability), FN-CAS-01 (case), FN-JOB-01 (job queue); IDR-02/03/06/07.
Engineering-lead decisions 2026-11-18: data.artifact lives in its own schema `data`
(as in DS-19 / TECHNICAL_DESIGN), and every table whose columns are specified in the DS
set is created here; tables without a column specification (governance.user, session,
role_grant, rejection, report, template*, frame_definition; clinical.cohort;
ops.backup_record, ops.blob_verification) are created by the tasks that own them.

Enumerations are CHECK constraints only where the full value set is specified in the
repository. Where it is not (scan.status, design_version.status, config_version.state,
measurement_value.provenance_class), the column is text NOT NULL and the owning task
adds the CHECK in its own migration.

No clinical, threshold or production value is defaulted here (DEC-029).
"""

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = ("clinical", "geometry", "governance", "data", "audit", "ops")
APP_SCHEMAS = ("clinical", "geometry", "governance", "data", "ops")
ROLES = ("app_rw", "worker_rw", "audit_append", "admin_ro")

FRAMES = ("F_file", "F_scan", "F_anat", "F_export")  # DS-01
ARTIFACT_KINDS = (  # DS-19
    "scan_original",
    "scan_mm",
    "scan_prepared",
    "positive",
    "display_lod",
    "deviation_field",
    "export_stl",
    "manifest",
    "report_pdf",
    "prescription_file",
    "integrity_report",
)
BUCKETS = ("scans", "artifacts", "exports", "reports", "prescriptions")  # DS-19, §3.1
FORMULA_TYPES = ("CI", "CVA", "CVAI_min_denominator", "CVAI_max_denominator", "HC")  # IDR-02
CONTOUR_RULES = ("enclosing_origin_projection", "largest_perimeter", "technician_pick")  # IDR-03
DIAGONAL_CENTRE_RULES = ("origin_projection", "contour_area_centroid")  # IDR-03
ANGLE_AXES = ("AP", "ML")  # IDR-03
OP_STATUSES = ("ok", "rejected", "failed", "pending")  # DS-04
JOB_STATUSES = ("queued", "running", "succeeded", "failed")  # DS-17
LANDMARK_ACTIONS = ("place", "move", "delete")  # DS-08
ANCHOR_FEATURES = ("face", "edge", "vertex")  # DS-07
PRESCRIPTION_MIME = ("application/pdf", "image/jpeg", "image/png")  # FN-CAS-06

# DS-06: |det - 1| <= 1e-9 (tolerance stated in the structure definition, not ad hoc).
DET_TOLERANCE = "1e-9"


def _in(col: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"CHECK ({col} IN ({quoted}))"


def _sha(col: str, *, null: bool = False) -> str:
    return f"{col} char(64) {'NULL' if null else 'NOT NULL'} CHECK ({col} ~ '^[0-9a-f]{{64}}$')"


def _vec(col: str, n: int, *, null: bool = False) -> str:
    """float8[n], one-dimensional, finite."""
    return (
        f"{col} float8[] {'NULL' if null else 'NOT NULL'} "
        f"CHECK (array_ndims({col}) = 1 AND array_length({col}, 1) = {n} "
        f"AND NOT ('NaN'::float8 = ANY({col}) OR 'Infinity'::float8 = ANY({col}) "
        f"OR '-Infinity'::float8 = ANY({col})))"
    )


def _finite(col: str) -> str:
    return f"CHECK ({col} NOT IN ('NaN'::float8, 'Infinity'::float8, '-Infinity'::float8))"


CREATED = "created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now()"

ROLES_SQL = [
    f"""
    DO $$ BEGIN
      IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{r}') THEN
        CREATE ROLE {r} NOLOGIN;
      END IF;
    END $$
    """
    for r in ROLES
]

SCHEMAS_SQL = [f"CREATE SCHEMA {s}" for s in SCHEMAS]

FUNCTIONS_SQL = [
    # Determinant of the rotation block of a row-major 4x4 matrix (DS-06).
    """
    CREATE FUNCTION geometry.rotation_det(m float8[]) RETURNS float8
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
      SELECT m[1] * (m[6] * m[11] - m[7] * m[10])
           - m[2] * (m[5] * m[11] - m[7] * m[9])
           + m[3] * (m[5] * m[10] - m[6] * m[9])
    $$
    """,
]

CLINICAL_SQL = [
    # DS-22, FN-CAS-01/03. No direct identifiers (DATA-10).
    f"""
    CREATE TABLE clinical."case" (
      case_id text PRIMARY KEY CHECK (case_id ~ '^J-[0-9A-HJKMNP-TV-Z]{{8}}$'),
      clinic_ref varchar(64) NULL,
      status text NOT NULL {_in("status", ("active", "archived"))},
      archived_by uuid NULL,
      archived_at timestamptz NULL,
      {CREATED},
      CHECK ((status = 'archived') = (archived_at IS NOT NULL AND archived_by IS NOT NULL))
    )
    """,
    f"""
    CREATE TABLE clinical.consent_ref (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      case_id text NOT NULL REFERENCES clinical."case"(case_id),
      reference text NOT NULL CHECK (length(reference) BETWEEN 1 AND 256),
      scope text NOT NULL,
      {CREATED}
    )
    """,
    f"""
    CREATE TABLE clinical.prescription (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      case_id text NOT NULL REFERENCES clinical."case"(case_id),
      {_sha("file_sha")},
      file_name text NOT NULL,
      mime text NOT NULL {_in("mime", PRESCRIPTION_MIME)},
      size_bytes bigint NOT NULL CHECK (size_bytes > 0),
      label text NULL,
      attached_by uuid NOT NULL,
      attached_at timestamptz NOT NULL DEFAULT now()
    )
    """,
]

GEOMETRY_SQL = [
    # FN-SCN-01; status set is defined by the scan tasks (no CHECK here).
    f"""
    CREATE TABLE geometry.scan (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      case_id text NOT NULL REFERENCES clinical."case"(case_id),
      status text NOT NULL,
      {_sha("original_sha")},
      file_name text NOT NULL,
      size_bytes bigint NOT NULL CHECK (size_bytes > 0),
      uploaded_by uuid NOT NULL,
      uploaded_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    # DS-22 scan metadata (clinical zone), one row per scan.
    """
    CREATE TABLE clinical.scan_metadata (
      scan_id uuid PRIMARY KEY REFERENCES geometry.scan(id),
      device text NULL,
      software text NULL,
      software_version text NULL,
      operator text NULL,
      acquisition_date date NULL,
      acquisition_date_unknown boolean NOT NULL,
      cap text NULL,
      posture text NULL,
      attempts integer NULL CHECK (attempts >= 1),
      locked boolean NOT NULL,
      updated_by uuid NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK (NOT (acquisition_date IS NOT NULL AND acquisition_date_unknown))
    )
    """,
    # FN-ANA-01
    f"""
    CREATE TABLE geometry.landmark_set (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      scan_id uuid NOT NULL REFERENCES geometry.scan(id),
      version integer NOT NULL CHECK (version >= 1),
      {_sha("reference_topology_sha")},
      frame_definition_id text NOT NULL,
      frame_definition_version integer NOT NULL CHECK (frame_definition_version >= 1),
      {CREATED},
      UNIQUE (scan_id, version)
    )
    """,
    # DS-07 anchor + DS-08 landmark
    f"""
    CREATE TABLE geometry.landmark (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      landmark_set_id uuid NOT NULL REFERENCES geometry.landmark_set(id),
      name text NOT NULL,
      {_sha("mesh_sha")},
      face_id integer NOT NULL CHECK (face_id >= 0),
      {_vec("bary", 3)},
      {_vec("xyz_mm_cache", 3)},
      snap_distance_mm float8 NOT NULL CHECK (snap_distance_mm >= 0) {_finite("snap_distance_mm")},
      feature text NOT NULL {_in("feature", ANCHOR_FEATURES)},
      placed_by uuid NOT NULL,
      placed_at timestamptz NOT NULL DEFAULT now(),
      CHECK (0 <= ALL (bary)),
      UNIQUE (landmark_set_id, name)
    )
    """,
    # DS-08 placement trail, append-only (DATA-15): app role gets INSERT/SELECT only.
    f"""
    CREATE TABLE geometry.landmark_history (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      landmark_set_id uuid NOT NULL REFERENCES geometry.landmark_set(id),
      name text NOT NULL,
      action text NOT NULL {_in("action", LANDMARK_ACTIONS)},
      anchor jsonb NULL,
      prev_anchor jsonb NULL,
      {CREATED},
      CHECK ((action = 'delete') = (anchor IS NULL)),
      CHECK ((action = 'place') = (prev_anchor IS NULL))
    )
    """,
    # DS-06 Transform4 (INV-06): rigid, no reflection, bottom row exact.
    f"""
    CREATE TABLE geometry.frame (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      scan_id uuid NOT NULL REFERENCES geometry.scan(id),
      landmark_set_id uuid NULL REFERENCES geometry.landmark_set(id),
      from_frame text NOT NULL {_in("from_frame", FRAMES)},
      to_frame text NOT NULL {_in("to_frame", FRAMES)},
      {_vec("matrix", 16)},
      det float8 NOT NULL {_finite("det")},
      provenance jsonb NOT NULL,
      confirmed_by uuid NULL,
      confirmed_at timestamptz NULL,
      {CREATED},
      CHECK (from_frame <> to_frame),
      CHECK (abs(det - 1) <= {DET_TOLERANCE}),
      CHECK (abs(det - geometry.rotation_det(matrix)) <= {DET_TOLERANCE}),
      CHECK (matrix[13] = 0 AND matrix[14] = 0 AND matrix[15] = 0 AND matrix[16] = 1),
      CHECK ((confirmed_at IS NULL) = (confirmed_by IS NULL))
    )
    """,
]

GOVERNANCE_SQL = [
    # DS-16; state values are defined by FN-CFG tasks. Exactly one active version.
    f"""
    CREATE TABLE governance.config_version (
      version integer PRIMARY KEY CHECK (version >= 1),
      document jsonb NOT NULL,
      test_only boolean NOT NULL,
      state text NOT NULL,
      diff jsonb NULL,
      {_sha("diff_sha", null=True)},
      controlled boolean NOT NULL,
      controlled_last_changed_by uuid NULL,
      controlled_last_changed_at timestamptz NULL,
      comment text NULL,
      published_by uuid NOT NULL,
      published_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE UNIQUE INDEX config_version_one_active ON governance.config_version ((true)) "
    "WHERE state = 'active'",
    # DS-10 + IDR-02/03. Immutable once published (no UPDATE grant).
    f"""
    CREATE TABLE governance.measurement_definition (
      id text NOT NULL,
      version integer NOT NULL CHECK (version >= 1),
      name_ru text NOT NULL,
      formula_type text NOT NULL {_in("formula_type", FORMULA_TYPES)},
      formula_text text NOT NULL,
      plane_rule jsonb NOT NULL,
      diagonal_angle_deg float8 NULL {_finite("diagonal_angle_deg")},
      contour_selection_rule text NOT NULL {_in("contour_selection_rule", CONTOUR_RULES)},
      diagonal_centre_rule text NOT NULL {_in("diagonal_centre_rule", DIAGONAL_CENTRE_RULES)},
      angle_reference_axis text NOT NULL {_in("angle_reference_axis", ANGLE_AXES)},
      frame_definition_id text NOT NULL,
      unit text NOT NULL,
      source_ref text NULL,
      {CREATED},
      PRIMARY KEY (id, version)
    )
    """,
]

GEOMETRY_SQL_2 = [
    # FN-MEA-01 provenance fields at set level.
    f"""
    CREATE TABLE geometry.measurement_set (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      frame_id uuid NOT NULL REFERENCES geometry.frame(id),
      config_version integer NOT NULL REFERENCES governance.config_version(version),
      {_sha("landmark_set_sha")},
      {_sha("source_mesh_sha")},
      software_version text NOT NULL,
      {CREATED}
    )
    """,
    # DS-11: no value without definition id+version (INV-05); no severity/threshold field
    # exists (FR-045). Immutable (no UPDATE grant).
    f"""
    CREATE TABLE geometry.measurement_value (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      measurement_set_id uuid NOT NULL REFERENCES geometry.measurement_set(id),
      name text NOT NULL,
      value float8 NULL {_finite("value")},
      not_computed_reason text NULL,
      unit text NOT NULL,
      definition_id text NOT NULL,
      definition_version integer NOT NULL,
      plane jsonb NOT NULL,
      frame_id uuid NOT NULL REFERENCES geometry.frame(id),
      computed_flag boolean NOT NULL,
      provenance_class text NOT NULL,
      synthetic_contact boolean NOT NULL,
      config_version integer NOT NULL REFERENCES governance.config_version(version),
      FOREIGN KEY (definition_id, definition_version)
        REFERENCES governance.measurement_definition(id, version),
      CHECK ((value IS NULL) = (not_computed_reason IS NOT NULL)),
      UNIQUE (measurement_set_id, name)
    )
    """,
    f"""
    CREATE TABLE geometry.design (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      case_id text NOT NULL REFERENCES clinical."case"(case_id),
      scan_id uuid NOT NULL REFERENCES geometry.scan(id),
      frame_id uuid NOT NULL REFERENCES geometry.frame(id),
      {CREATED}
    )
    """,
    # DS-23; status values are defined by FN-REV-06 (07 §8.1, not in this repository).
    f"""
    CREATE TABLE geometry.design_version (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      design_id uuid NOT NULL REFERENCES geometry.design(id),
      number integer NOT NULL CHECK (number >= 1),
      parent_id uuid NULL REFERENCES geometry.design_version(id),
      status text NOT NULL,
      {_sha("scan_sha")},
      frame_id uuid NOT NULL REFERENCES geometry.frame(id),
      config_version integer NOT NULL REFERENCES governance.config_version(version),
      template_ref text NULL,
      {_sha("params_sha", null=True)},
      {_sha("geometry_sha", null=True)},
      kernel_version text NULL,
      kernel_image_digest text NULL CHECK (kernel_image_digest ~ '^sha256:[0-9a-f]{{64}}$'),
      regen_failed boolean NOT NULL DEFAULT false,
      {CREATED},
      UNIQUE (design_id, number),
      UNIQUE (id, geometry_sha),
      CHECK (parent_id IS DISTINCT FROM id)
    )
    """,
    # DS-04 op-log entry.
    f"""
    CREATE TABLE geometry.operation (
      design_version_id uuid NOT NULL REFERENCES geometry.design_version(id),
      seq integer NOT NULL CHECK (seq >= 1),
      type text NOT NULL,
      op_version integer NOT NULL CHECK (op_version >= 1),
      params jsonb NOT NULL,
      enabled boolean NOT NULL,
      status text NOT NULL {_in("status", OP_STATUSES)},
      reason_code text NULL,
      report jsonb NULL,
      {CREATED},
      PRIMARY KEY (design_version_id, seq)
    )
    """,
    # DS-25, bound to geometry_sha. Immutable (no UPDATE grant).
    f"""
    CREATE TABLE geometry.validity_report (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      {_sha("geometry_sha")},
      kernel_version text NOT NULL,
      checks jsonb NOT NULL,
      passed boolean NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (geometry_sha, kernel_version)
    )
    """,
]

GOVERNANCE_SQL_2 = [
    # DS-20 / DATA-05. INV-04: the composite FK pins geometry_sha to the version's hash.
    # FR-182: no approval without prescription_sha.
    f"""
    CREATE TABLE governance.approval (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      design_version_id uuid NOT NULL,
      {_sha("geometry_sha")},
      {_sha("params_sha")},
      {_sha("scan_sha")},
      measurement_set_id uuid NOT NULL REFERENCES geometry.measurement_set(id),
      {_sha("prescription_sha")},
      checklist_version integer NOT NULL CHECK (checklist_version >= 1),
      checklist_answers jsonb NOT NULL,
      config_version integer NOT NULL REFERENCES governance.config_version(version),
      controlled_section_last_change timestamptz NULL,
      self_approval boolean NOT NULL,
      statement_text text NOT NULL CHECK (length(statement_text) > 0),
      approver_id uuid NOT NULL,
      approver_role text NOT NULL,
      at_utc timestamptz NOT NULL DEFAULT now(),
      reapproval_required boolean NOT NULL DEFAULT false,
      FOREIGN KEY (design_version_id, geometry_sha)
        REFERENCES geometry.design_version(id, geometry_sha)
    )
    """,
    # DS-21: released => re-import passed and both files present (FR-102/103).
    f"""
    CREATE TABLE governance.export (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      design_version_id uuid NOT NULL REFERENCES geometry.design_version(id),
      approval_id uuid NOT NULL REFERENCES governance.approval(id),
      {_sha("stl_sha", null=True)},
      {_sha("manifest_sha", null=True)},
      {_vec("export_frame", 16)},
      reimport_passed boolean NULL,
      reimport_max_dev_mm float8 NULL {_finite("reimport_max_dev_mm")},
      reimport_tolerance_mm float8 NULL {_finite("reimport_tolerance_mm")},
      released boolean NOT NULL,
      {CREATED},
      CHECK (NOT released OR (reimport_passed AND stl_sha IS NOT NULL
                              AND manifest_sha IS NOT NULL))
    )
    """,
]

DATA_SQL = [
    # DS-19. Immutable (INV-02: no UPDATE/DELETE grant). One case per row (INV-01).
    f"""
    CREATE TABLE data.artifact (
      case_id text NOT NULL REFERENCES clinical."case"(case_id),
      {_sha("sha256")},
      kind text NOT NULL {_in("kind", ARTIFACT_KINDS)},
      parent_shas char(64)[] NOT NULL DEFAULT '{{}}',
      frame text NULL {_in("frame", FRAMES)},
      units text NULL,
      stats jsonb NULL,
      lib_versions jsonb NULL,
      display_only boolean NOT NULL,
      bucket text NOT NULL {_in("bucket", BUCKETS)},
      size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (case_id, sha256),
      CHECK ((kind = 'prescription_file') = (bucket = 'prescriptions'))
    )
    """,
]

AUDIT_SQL = [
    # DS-18 / IDR-06: hashed core; summaries live outside the hash in an erasable table.
    f"""
    CREATE TABLE audit.audit_event (
      seq bigint PRIMARY KEY CHECK (seq >= 1),
      type text NOT NULL,
      user_id uuid NULL,
      role text NULL,
      object_type text NULL,
      object_id text NULL,
      object_version integer NULL,
      case_id text NULL,
      at_utc timestamptz NOT NULL,
      {_sha("prev_hash", null=True)},
      {_sha("hash")},
      CHECK ((seq = 1) = (prev_hash IS NULL))
    )
    """,
    """
    CREATE TABLE audit.audit_summary (
      seq bigint PRIMARY KEY REFERENCES audit.audit_event(seq),
      summary_before jsonb NULL,
      summary_after jsonb NULL
    )
    """,
    f"""
    CREATE TABLE audit.chain_head (
      id boolean PRIMARY KEY DEFAULT true CHECK (id),
      last_seq bigint NOT NULL CHECK (last_seq >= 0),
      {_sha("last_hash", null=True)},
      CHECK ((last_seq = 0) = (last_hash IS NULL))
    )
    """,
    "INSERT INTO audit.chain_head (id, last_seq, last_hash) VALUES (true, 0, NULL)",
    # Core rows are never changed or removed, by any role (FR-121, SEC-03).
    """
    CREATE FUNCTION audit.forbid_change() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
      -- Default SQLSTATE P0001 (not 42501) so tests can tell the trigger from missing grants.
      RAISE EXCEPTION 'audit.audit_event is append-only (% refused)', TG_OP;
    END $$
    """,
    "CREATE TRIGGER audit_event_no_update_delete BEFORE UPDATE OR DELETE ON audit.audit_event "
    "FOR EACH ROW EXECUTE FUNCTION audit.forbid_change()",
    "CREATE TRIGGER audit_event_no_truncate BEFORE TRUNCATE ON audit.audit_event "
    "FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_change()",
    # FN-AUD-06 step 1: chain_head moves only through this SECURITY DEFINER function.
    # The caller (IF-08, FN-AUD-01) computes hash = SHA-256(prev_hash || JCS(core)); this
    # function serialises appends and enforces seq/prev_hash continuity.
    """
    CREATE FUNCTION audit.append_event(
      p_seq bigint, p_type text, p_user_id uuid, p_role text,
      p_object_type text, p_object_id text, p_object_version integer, p_case_id text,
      p_at_utc timestamptz, p_prev_hash char(64), p_hash char(64),
      p_summary_before jsonb DEFAULT NULL, p_summary_after jsonb DEFAULT NULL
    ) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    DECLARE
      head audit.chain_head%ROWTYPE;
    BEGIN
      SELECT * INTO head FROM audit.chain_head WHERE id FOR UPDATE;
      IF p_seq <> head.last_seq + 1 THEN
        RAISE EXCEPTION 'audit seq % does not follow chain head %', p_seq, head.last_seq
          USING ERRCODE = 'serialization_failure';
      END IF;
      IF p_prev_hash IS DISTINCT FROM head.last_hash THEN
        RAISE EXCEPTION 'audit prev_hash does not match chain head at seq %', head.last_seq
          USING ERRCODE = 'serialization_failure';
      END IF;
      INSERT INTO audit.audit_event (seq, type, user_id, role, object_type, object_id,
                                     object_version, case_id, at_utc, prev_hash, hash)
      VALUES (p_seq, p_type, p_user_id, p_role, p_object_type, p_object_id,
              p_object_version, p_case_id, p_at_utc, p_prev_hash, p_hash);
      IF p_summary_before IS NOT NULL OR p_summary_after IS NOT NULL THEN
        INSERT INTO audit.audit_summary (seq, summary_before, summary_after)
        VALUES (p_seq, p_summary_before, p_summary_after);
      END IF;
      UPDATE audit.chain_head SET last_seq = p_seq, last_hash = p_hash WHERE id;
      RETURN p_seq;
    END $$
    """,
]

OPS_SQL = [
    # DS-17 / IF-02 / FN-JOB-01..02. Type names are versioned (e.g. regenerate.v1).
    f"""
    CREATE TABLE ops.job (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      type text NOT NULL CHECK (type ~ '^[a-z][a-z0-9_.]*\\.v[0-9]+$'),
      status text NOT NULL {_in("status", JOB_STATUSES)},
      payload jsonb NOT NULL,
      idempotent boolean NOT NULL,
      case_id text NULL REFERENCES clinical."case"(case_id),
      requested_by uuid NOT NULL,
      idempotency_key text NULL,
      result jsonb NULL,
      error_code text NULL,
      attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
      lease_until timestamptz NULL,
      heartbeat_at timestamptz NULL,
      worker_id text NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      finished_at timestamptz NULL,
      CHECK (status <> 'running' OR (lease_until IS NOT NULL AND worker_id IS NOT NULL)),
      CHECK ((status IN ('succeeded', 'failed')) = (finished_at IS NOT NULL)),
      CHECK (status <> 'failed' OR error_code IS NOT NULL)
    )
    """,
    "CREATE INDEX job_claim_queue ON ops.job (created_at) WHERE status = 'queued'",
    "CREATE INDEX job_lease_reaper ON ops.job (lease_until) WHERE status = 'running'",
    # FN-API idempotent replay: (user, key, status, body hash, body).
    f"""
    CREATE TABLE ops.idempotency_key (
      user_id uuid NOT NULL,
      key text NOT NULL CHECK (length(key) BETWEEN 1 AND 128),
      status_code integer NOT NULL CHECK (status_code BETWEEN 100 AND 599),
      {_sha("body_sha")},
      body jsonb NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id, key)
    )
    """,
]

# Least privilege (IDR-07, FN-AUD-06). Roles are NOLOGIN groups; login users are created
# per deployment (no credentials in migrations) and granted membership.
APPEND_ONLY_OR_IMMUTABLE = (
    "data.artifact",
    "geometry.landmark_history",
    "geometry.measurement_value",
    "geometry.validity_report",
    "governance.measurement_definition",
)
APP_DELETABLE = ("geometry.operation", "geometry.landmark", "ops.idempotency_key")

GRANTS_SQL = [
    *(f"REVOKE ALL ON SCHEMA {s} FROM PUBLIC" for s in SCHEMAS),
    "REVOKE ALL ON FUNCTION audit.append_event FROM PUBLIC",
    "REVOKE ALL ON FUNCTION audit.forbid_change FROM PUBLIC",
    # app_rw: domain read/write; no audit access; no deletes except draft-editable rows.
    *(f"GRANT USAGE ON SCHEMA {s} TO app_rw" for s in APP_SCHEMAS),
    *(f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA {s} TO app_rw" for s in APP_SCHEMAS),
    *(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA {s} TO app_rw" for s in APP_SCHEMAS),
    *(f"REVOKE UPDATE ON {t} FROM app_rw" for t in APPEND_ONLY_OR_IMMUTABLE),
    *(f"GRANT DELETE ON {t} TO app_rw" for t in APP_DELETABLE),
    # worker_rw: job queue only (claim, lease, heartbeat, result).
    "GRANT USAGE ON SCHEMA ops TO worker_rw",
    "GRANT SELECT, UPDATE ON ops.job TO worker_rw",
    # audit_append: INSERT/SELECT on the log; chain head only via append_event (FN-AUD-06).
    "GRANT USAGE ON SCHEMA audit TO audit_append",
    "GRANT SELECT, INSERT ON audit.audit_event, audit.audit_summary TO audit_append",
    "GRANT SELECT ON audit.chain_head TO audit_append",
    "GRANT EXECUTE ON FUNCTION audit.append_event TO audit_append",
    # admin_ro: read everything, change nothing.
    *(f"GRANT USAGE ON SCHEMA {s} TO admin_ro" for s in SCHEMAS),
    *(f"GRANT SELECT ON ALL TABLES IN SCHEMA {s} TO admin_ro" for s in SCHEMAS),
]


def upgrade() -> None:
    for stmt in (
        *ROLES_SQL,
        *SCHEMAS_SQL,
        *FUNCTIONS_SQL,
        *CLINICAL_SQL,
        *GEOMETRY_SQL,
        *GOVERNANCE_SQL,
        *GEOMETRY_SQL_2,
        *GOVERNANCE_SQL_2,
        *DATA_SQL,
        *AUDIT_SQL,
        *OPS_SQL,
        *GRANTS_SQL,
    ):
        op.execute(stmt)


def downgrade() -> None:
    raise NotImplementedError("forward-only migrations: write a new migration instead")
