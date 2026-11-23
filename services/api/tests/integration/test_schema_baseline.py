"""IT-schema / TC-DATA-*: baseline migration on an empty database (XC-FND-05).

Completion criteria: migration up on an empty DB passes; the audit role cannot
UPDATE/DELETE (FN-AUD-06, FR-121, SEC-03). Plus grants per role and the CHECK constraints.
All rows are synthetic.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
import hashlib
import uuid

from alembic import command
from alembic.script import ScriptDirectory
import psycopg
from psycopg import errors
import pytest

from jude_api.db.migrate import alembic_config, upgrade

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]

USER = uuid.UUID("00000000-0000-4000-8000-000000000001")
HEAD = ScriptDirectory.from_config(alembic_config("postgresql://unused")).get_current_head()
IDENTITY = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]

EXPECTED_TABLES = {
    ("clinical", "case"),
    ("clinical", "consent_ref"),
    ("clinical", "prescription"),
    ("clinical", "scan_metadata"),
    ("geometry", "scan"),
    ("geometry", "landmark_set"),
    ("geometry", "landmark"),
    ("geometry", "landmark_history"),
    ("geometry", "frame"),
    ("geometry", "measurement_set"),
    ("geometry", "measurement_value"),
    ("geometry", "design"),
    ("geometry", "design_version"),
    ("geometry", "operation"),
    ("geometry", "validity_report"),
    ("governance", "config_version"),
    ("governance", "measurement_definition"),
    ("governance", "approval"),
    ("governance", "export"),
    ("data", "artifact"),
    ("audit", "audit_event"),
    ("audit", "audit_summary"),
    ("audit", "chain_head"),
    ("ops", "job"),
    ("ops", "idempotency_key"),
    # 0003_iam_accounts (TSK-IAM-01-B)
    ("governance", "user"),
    ("governance", "login_failure"),
    ("governance", "session"),
}
SCHEMAS = {"clinical", "geometry", "governance", "data", "audit", "ops"}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@contextmanager
def as_role(conn: Conn, role: str) -> Iterator[None]:
    conn.execute(f"SET ROLE {role}")
    try:
        yield
    finally:
        conn.execute("RESET ROLE")


def refused(
    conn: Conn, exc: type[Exception], sql: str, params: Sequence[object] | None = None
) -> None:
    """Assert the statement fails with exc; the savepoint keeps the outer transaction usable."""
    with pytest.raises(exc), conn.transaction():
        conn.execute(sql, params)


def ok(conn: Conn, sql: str, params: Sequence[object] | None = None) -> None:
    with conn.transaction():
        conn.execute(sql, params)


# --- seed helpers (owner role) --------------------------------------------------------------


def make_case(conn: Conn, case_id: str = "J-0123ABCD") -> str:
    conn.execute(
        """INSERT INTO clinical."case" (case_id, status, created_by) VALUES (%s, 'active', %s)""",
        (case_id, USER),
    )
    return case_id


def make_scan(conn: Conn, case_id: str) -> uuid.UUID:
    row = conn.execute(
        """INSERT INTO geometry.scan (case_id, status, original_sha, file_name, size_bytes,
               uploaded_by) VALUES (%s, 'uploaded', %s, 'phantom_T1.stl', 84, %s) RETURNING id""",
        (case_id, sha("scan"), USER),
    ).fetchone()
    assert row is not None
    return row[0]  # type: ignore[return-value]


def make_frame(conn: Conn, scan_id: uuid.UUID) -> uuid.UUID:
    row = conn.execute(
        """INSERT INTO geometry.frame (scan_id, from_frame, to_frame, matrix, det, provenance,
               created_by) VALUES (%s, 'F_scan', 'F_anat', %s, 1.0, '{}', %s) RETURNING id""",
        (scan_id, IDENTITY, USER),
    ).fetchone()
    assert row is not None
    return row[0]  # type: ignore[return-value]


def make_config(conn: Conn, version: int = 1, state: str = "active") -> int:
    conn.execute(
        """INSERT INTO governance.config_version (version, document, test_only, state,
               controlled, published_by)
           VALUES (%s, '{"schema": "config/1"}', true, %s, false, %s)""",
        (version, state, USER),
    )
    return version


# --- migration --------------------------------------------------------------------------------


def test_head_applied_on_empty_db(conn: Conn) -> None:
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row == (HEAD,)


def test_six_schemas(conn: Conn) -> None:
    rows = conn.execute(
        "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)", (list(SCHEMAS),)
    ).fetchall()
    assert {r[0] for r in rows} == SCHEMAS


def test_tables(conn: Conn) -> None:
    rows = conn.execute(
        """SELECT table_schema, table_name FROM information_schema.tables
           WHERE table_schema = ANY(%s) AND table_type = 'BASE TABLE'""",
        (list(SCHEMAS),),
    ).fetchall()
    assert set(rows) == EXPECTED_TABLES


def test_roles_are_nologin_groups(conn: Conn) -> None:
    rows = conn.execute(
        "SELECT rolname, rolcanlogin, rolsuper FROM pg_roles WHERE rolname = ANY(%s)",
        (["app_rw", "worker_rw", "audit_append", "admin_ro"],),
    ).fetchall()
    assert sorted(rows) == sorted(
        (r, False, False) for r in ("app_rw", "worker_rw", "audit_append", "admin_ro")
    )


def test_second_empty_db_with_existing_roles_and_rerun_is_noop(
    migrated_url: str, empty_db_url: str
) -> None:
    """Roles are cluster-wide: a second database must migrate although they already exist."""
    upgrade(empty_db_url)
    upgrade(empty_db_url)  # already at head: no-op
    with psycopg.connect(empty_db_url) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (HEAD,)


def test_downgrade_is_refused(migrated_url: str) -> None:
    with pytest.raises(NotImplementedError):
        command.downgrade(alembic_config(migrated_url), "base")


# --- audit immutability (FN-AUD-06, FR-121, SEC-03) -----------------------------------------

APPEND = (
    "SELECT audit.append_event(%s, 'case.created', %s, 'clinic_admin', 'case', %s, 1, %s,"
    " now(), %s, %s)"
)


def test_audit_append_chain(conn: Conn) -> None:
    h1, h2 = sha("e1"), sha("e2")
    with as_role(conn, "audit_append"):
        ok(conn, APPEND, (1, USER, "J-0123ABCD", "J-0123ABCD", None, h1))
        ok(conn, APPEND, (2, USER, "J-0123ABCD", "J-0123ABCD", h1, h2))
        head = conn.execute("SELECT last_seq, last_hash FROM audit.chain_head").fetchone()
    assert head == (2, h2)


def test_audit_append_rejects_broken_chain(conn: Conn) -> None:
    h1 = sha("e1")
    with as_role(conn, "audit_append"):
        ok(conn, APPEND, (1, USER, "x", None, None, h1))
        refused(conn, errors.SerializationFailure, APPEND, (3, USER, "x", None, h1, sha("e3")))
        refused(
            conn, errors.SerializationFailure, APPEND, (2, USER, "x", None, sha("no"), sha("e2"))
        )


def test_audit_role_cannot_update_or_delete(conn: Conn) -> None:
    with as_role(conn, "audit_append"):
        ok(conn, APPEND, (1, USER, "x", None, None, sha("e1")))
        refused(conn, errors.InsufficientPrivilege, "UPDATE audit.audit_event SET type = 'x'")
        refused(conn, errors.InsufficientPrivilege, "DELETE FROM audit.audit_event")
        refused(conn, errors.InsufficientPrivilege, "TRUNCATE audit.audit_event")
        refused(
            conn,
            errors.InsufficientPrivilege,
            "UPDATE audit.audit_summary SET summary_after = '{}'",
        )
        refused(conn, errors.InsufficientPrivilege, "DELETE FROM audit.audit_summary")
        refused(conn, errors.InsufficientPrivilege, "UPDATE audit.chain_head SET last_seq = 0")


def test_audit_core_immutable_even_for_owner(conn: Conn) -> None:
    ok(conn, APPEND, (1, USER, "x", None, None, sha("e1")))
    refused(conn, errors.RaiseException, "UPDATE audit.audit_event SET type = 'x'")
    refused(conn, errors.RaiseException, "DELETE FROM audit.audit_event")
    refused(conn, errors.RaiseException, "TRUNCATE audit.audit_event CASCADE")


def test_append_function_not_executable_by_others(conn: Conn) -> None:
    for role in ("app_rw", "worker_rw", "admin_ro"):
        with as_role(conn, role):
            refused(
                conn, errors.InsufficientPrivilege, APPEND, (1, USER, "x", None, None, sha("e"))
            )


# --- grants per role ------------------------------------------------------------------------


def test_app_role_has_no_audit_access(conn: Conn) -> None:
    with as_role(conn, "app_rw"):
        refused(conn, errors.InsufficientPrivilege, "SELECT * FROM audit.audit_event")


def test_app_role_cannot_change_immutable_rows(conn: Conn) -> None:
    case_id = make_case(conn)
    conn.execute(
        """INSERT INTO data.artifact (case_id, sha256, kind, display_only, bucket, size_bytes)
           VALUES (%s, %s, 'scan_original', false, 'scans', 84)""",
        (case_id, sha("a")),
    )
    with as_role(conn, "app_rw"):
        ok(conn, "SELECT count(*) FROM data.artifact")
        refused(conn, errors.InsufficientPrivilege, "UPDATE data.artifact SET size_bytes = 1")
        refused(conn, errors.InsufficientPrivilege, "DELETE FROM data.artifact")
        refused(conn, errors.InsufficientPrivilege, """DELETE FROM clinical."case" """)
        refused(
            conn, errors.InsufficientPrivilege, "UPDATE geometry.landmark_history SET name = 'x'"
        )


def test_worker_role_limited_to_job_queue(conn: Conn) -> None:
    make_case(conn)
    with as_role(conn, "worker_rw"):
        refused(conn, errors.InsufficientPrivilege, """SELECT * FROM clinical."case" """)
        refused(conn, errors.InsufficientPrivilege, "SELECT * FROM data.artifact")
        refused(conn, errors.InsufficientPrivilege, "SELECT * FROM audit.audit_event")
        ok(conn, "UPDATE ops.job SET heartbeat_at = now() WHERE false")
        refused(conn, errors.InsufficientPrivilege, "DELETE FROM ops.job")


def test_admin_ro_reads_but_never_writes(conn: Conn) -> None:
    with as_role(conn, "admin_ro"):
        ok(conn, "SELECT count(*) FROM audit.audit_event")
        ok(conn, """SELECT count(*) FROM clinical."case" """)
        refused(
            conn,
            errors.InsufficientPrivilege,
            """INSERT INTO clinical."case" (case_id, status, created_by)
               VALUES ('J-00000000', 'active', %s)""",
            (USER,),
        )


# --- CHECK constraints and integrity -------------------------------------------------------


@pytest.mark.parametrize(
    "bad", ["J-0123abcd", "J-0123ABCI", "X-0123ABCD", "J-0123ABC", "J-0123ABCDE"]
)
def test_case_id_format(conn: Conn, bad: str) -> None:
    refused(
        conn,
        errors.CheckViolation,
        """INSERT INTO clinical."case" (case_id, status, created_by) VALUES (%s, 'active', %s)""",
        (bad, USER),
    )


def test_frame_rigid_transform_checks(conn: Conn) -> None:
    scan_id = make_scan(conn, make_case(conn))
    insert = """INSERT INTO geometry.frame (scan_id, from_frame, to_frame, matrix, det,
                    provenance, created_by) VALUES (%s, 'F_scan', 'F_anat', %s, %s, '{}', %s)"""
    ok(conn, insert, (scan_id, IDENTITY, 1.0, USER))
    reflection = list(IDENTITY)
    reflection[0] = -1.0
    refused(conn, errors.CheckViolation, insert, (scan_id, reflection, -1.0, USER))
    # det claimed 1 but the matrix scales by 2: the computed determinant disagrees
    scaled = [2.0 if i in (0, 5, 10) else v for i, v in enumerate(IDENTITY)]
    refused(conn, errors.CheckViolation, insert, (scan_id, scaled, 1.0, USER))
    bottom = list(IDENTITY)
    bottom[12] = 5.0
    refused(conn, errors.CheckViolation, insert, (scan_id, bottom, 1.0, USER))
    refused(conn, errors.CheckViolation, insert, (scan_id, IDENTITY[:12], 1.0, USER))
    refused(conn, errors.CheckViolation, insert, (scan_id, IDENTITY, 1.0 + 1e-6, USER))


def test_job_constraints(conn: Conn) -> None:
    insert = """INSERT INTO ops.job (type, status, payload, idempotent, requested_by, lease_until,
                    worker_id) VALUES (%s, %s, '{}', true, %s, %s, %s)"""
    ok(conn, insert, ("regenerate.v1", "queued", USER, None, None))
    refused(conn, errors.CheckViolation, insert, ("regenerate", "queued", USER, None, None))
    refused(conn, errors.CheckViolation, insert, ("regenerate.v1", "done", USER, None, None))
    refused(conn, errors.CheckViolation, insert, ("regenerate.v1", "running", USER, None, None))


def test_artifact_kind_and_bucket(conn: Conn) -> None:
    case_id = make_case(conn)
    insert = """INSERT INTO data.artifact (case_id, sha256, kind, display_only, bucket, size_bytes)
                VALUES (%s, %s, %s, false, %s, 1)"""
    ok(conn, insert, (case_id, sha("p"), "prescription_file", "prescriptions"))
    refused(conn, errors.CheckViolation, insert, (case_id, sha("q"), "photo", "artifacts"))
    refused(
        conn, errors.CheckViolation, insert, (case_id, sha("r"), "prescription_file", "artifacts")
    )
    refused(conn, errors.CheckViolation, insert, (case_id, sha("s"), "positive", "prescriptions"))
    refused(conn, errors.CheckViolation, insert, (case_id, "NOT-A-SHA", "positive", "artifacts"))


def test_measurement_definition_enums(conn: Conn) -> None:
    insert = """INSERT INTO governance.measurement_definition (id, version, name_ru, formula_type,
                    formula_text, plane_rule, contour_selection_rule, diagonal_centre_rule,
                    angle_reference_axis, frame_definition_id, unit, created_by)
                VALUES ('def-1', %s, 'синтетика', %s, 'text', '{}', %s, 'origin_projection',
                        'AP', 'fd-1', 'mm', %s)"""
    ok(conn, insert, (1, "HC", "enclosing_origin_projection", USER))
    refused(
        conn, errors.CheckViolation, insert, (2, "SEVERITY", "enclosing_origin_projection", USER)
    )
    refused(conn, errors.CheckViolation, insert, (3, "HC", "nearest", USER))


APPROVAL_INSERT = """INSERT INTO governance.approval (design_version_id, geometry_sha,
        params_sha, scan_sha, measurement_set_id, prescription_sha, checklist_version,
        checklist_answers, config_version, self_approval, statement_text, approver_id,
        approver_role)
    VALUES (%s, %s, %s, %s, %s, %s, 1, '{}', %s, false, 'statement', %s, 'technician')
    RETURNING id"""


def make_saved_version(conn: Conn) -> tuple[object, ...]:
    """Seed case -> scan -> frame -> config -> measurement set -> design version.

    Returns the approval argument tuple for APPROVAL_INSERT.
    """
    case_id = make_case(conn)
    scan_id = make_scan(conn, case_id)
    frame_id = make_frame(conn, scan_id)
    cfg = make_config(conn)
    ms = conn.execute(
        """INSERT INTO geometry.measurement_set (frame_id, config_version, landmark_set_sha,
               source_mesh_sha, software_version, created_by) VALUES (%s, %s, %s, %s, '0.0.0', %s)
           RETURNING id""",
        (frame_id, cfg, sha("ls"), sha("mesh"), USER),
    ).fetchone()
    design = conn.execute(
        """INSERT INTO geometry.design (case_id, scan_id, frame_id, created_by)
           VALUES (%s, %s, %s, %s) RETURNING id""",
        (case_id, scan_id, frame_id, USER),
    ).fetchone()
    assert ms is not None and design is not None
    version = conn.execute(
        """INSERT INTO geometry.design_version (design_id, number, status, scan_sha, frame_id,
               config_version, params_sha, geometry_sha, created_by)
           VALUES (%s, 1, 'saved', %s, %s, %s, %s, %s, %s) RETURNING id""",
        (design[0], sha("scan"), frame_id, cfg, sha("params"), sha("geom"), USER),
    ).fetchone()
    assert version is not None
    return (version[0], sha("geom"), sha("params"), sha("scan"), ms[0], sha("rx"), cfg, USER)


def test_approval_pinned_to_version_geometry_sha(conn: Conn) -> None:
    args = make_saved_version(conn)
    ok(conn, APPROVAL_INSERT, args)
    wrong_geometry = (args[0], sha("other"), *args[2:])
    refused(conn, errors.ForeignKeyViolation, APPROVAL_INSERT, wrong_geometry)
    no_prescription = (*args[:5], None, *args[6:])
    refused(conn, errors.NotNullViolation, APPROVAL_INSERT, no_prescription)


def test_export_release_requires_reimport_pass(conn: Conn) -> None:
    args = make_saved_version(conn)
    approval = conn.execute(APPROVAL_INSERT, args).fetchone()
    assert approval is not None
    insert = """INSERT INTO governance.export (design_version_id, approval_id, stl_sha,
                    manifest_sha, export_frame, reimport_passed, released, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
    base = (args[0], approval[0])
    ok(conn, insert, (*base, sha("stl"), sha("man"), IDENTITY, True, True, USER))
    ok(conn, insert, (*base, None, None, IDENTITY, False, False, USER))
    refused(
        conn,
        errors.CheckViolation,
        insert,
        (*base, sha("stl"), sha("man"), IDENTITY, False, True, USER),
    )
    refused(
        conn, errors.CheckViolation, insert, (*base, None, sha("man"), IDENTITY, True, True, USER)
    )


def test_single_active_config_version(conn: Conn) -> None:
    make_config(conn, 1, "active")
    refused(
        conn,
        errors.UniqueViolation,
        """INSERT INTO governance.config_version (version, document, test_only, state, controlled,
               published_by) VALUES (2, '{}', true, 'active', false, %s)""",
        (USER,),
    )


IDENTITY_COLUMNS = {
    "patient_name",
    "first_name",
    "last_name",
    "full_name",
    "surname",
    "iin",
    "address",
    "phone",
    "email",
    "dob",
    "date_of_birth",
    "birth_date",
}


def test_no_direct_identifier_columns(conn: Conn) -> None:
    """DATA-10 / FN-CAS-01: no structured identity fields anywhere."""
    rows = conn.execute(
        """SELECT table_schema, table_name, column_name FROM information_schema.columns
           WHERE table_schema = ANY(%s) AND column_name = ANY(%s)""",
        (list(SCHEMAS), list(IDENTITY_COLUMNS)),
    ).fetchall()
    assert rows == []


def test_no_severity_or_threshold_fields(conn: Conn) -> None:
    """FR-045: measurement values carry no severity, grade or threshold field."""
    rows = conn.execute(
        """SELECT table_name, column_name FROM information_schema.columns
           WHERE table_schema = ANY(%s)
             AND (column_name ~ '(severity|threshold|grade|diagnos|classification)')""",
        (list(SCHEMAS),),
    ).fetchall()
    assert rows == []
