# Data Structures and Interfaces v1.0

| Field | Value |
|---|---|
| Document | DATA_STRUCTURES_AND_INTERFACES_v1.0.md |
| Version / date | v1.0 · 2026-11-15 |
| Status | Draft v1.0 for review — engineering proposal. **Not approved**; no decision in this set is final until signed by the engineering lead (ADR/TD status "Proposed"). |

## 1. Data structures

| ID | Name | Kind | Layer | Definition | Invariants | Store | Schema/version |
|---|---|---|---|---|---|---|---|
| DS-01 | MeshArrays | In-memory kernel value | Geometry Engine | V: float64[n,3] C-contiguous little-endian, mm, frame tag; F: int32[m,3] (counter-clockwise = outward on closed solids); optional face_tags: uint8[m] bit flags {1 scan, 2 cut, 4 wall, 8 cap, 16 synthetic}; optional vertex_attrs: dict[str, float64[n]]; frame: enum {F_file, F_scan, F_anat, F_export}; display_only: bool | finite V; 0 ≤ F < n; −0.0 canonicalised; display_only meshes are never kernel inputs (INV-10); n, m ≤ caps (SEC-07) | Blob (DS-19) as .npz-like canonical container "jude-arr/1" (header + raw arrays) addressed by SHA-256 of bytes; geometry_sha (DS-ALG-54) stored separately | jude-arr/1 |
| DS-02 | IntegrityReport | JSON document | Validation | {schema:"integrity/1", mesh_sha, kernel_version, n_vertices, n_faces, n_components, components[], boundary_loops[{id, n_vertices, perimeter_mm, bbox}], n_nonmanifold_edges, n_nonmanifold_vertices, n_degenerate, n_inconsistent_edges, self_intersecting_pairs, watertight, volume_mm3\|null, bbox_mm{min,max}, samples{…≤100}} | All counts exact integers; reproducible for same mesh_sha + kernel_version | Postgres jsonb (geometry schema) + blob copy | integrity/1 |
| DS-03 | OpSpec (registry entry) | Code-level registry record | Geometry Engine | {type:str, version:int, params_schema: JSON Schema 2020-12 (no defaults for clinical/production values), input_kinds[], output_kinds[], topology_preserving:bool, guard: bool} | Every behaviour change bumps version (FN-KRP-04) | Code + published JSON Schemas (versioned with code) | op-registry/1 |
| DS-04 | OperationRecord (op-log entry) | Persistent record | Domain | {design_version_id, seq:int, type, op_version, params: jsonb (units in key names, e.g. magnitude_mm), enabled:bool, status ∈ {ok, rejected, failed, pending}, report: jsonb, created_by, created_at} | seq contiguous 1..k; params validate against OpSpec.params_schema; saved versions immutable (INV-03) | Postgres geometry.operation | — |
| DS-05 | OpResult | Kernel return value | Geometry Engine | {status ∈ {ok, rejected, failed}, outputs: {name: DS-01}, report: dict, reason_code?: str, kernel_version, lib_versions: dict, timings_ms: dict (diagnostic, excluded from hashes)} | rejected/failed never carry output geometry used downstream (SAF-09) | Worker → job result (Postgres) + blobs | — |
| DS-06 | Transform4 | Value + persistent record | Geometry Engine | {matrix: float64[16] row-major, from_frame, to_frame, det: float64, provenance: {landmark_set_id \| config rule ref}} | \|det − 1\| ≤ 1e-9; ‖RᵀR − I‖_F ≤ 1e-9; no reflection (INV-06) | Postgres geometry.frame (+ CHECK on det) | — |
| DS-07 | Anchor | Value | Geometry Engine | {mesh_sha, face_id:int32, bary: float64[3] (sum 1, each ≥ 0), xyz_mm_cache: float64[3], snap_distance_mm, feature ∈ {face, edge, vertex}} | Valid only on meshes with the same topology as mesh_sha lineage (FN-KAN-02) | Postgres geometry.landmark / operation params | — |
| DS-08 | Landmark + placement trail | Persistent records | Domain | landmark{landmark_set_id, name (from frame definition), anchor DS-07, placed_by/at}; landmark_history{…, action ∈ {place, move, delete}, prev_anchor} | History append-only (DATA-15); stored coordinates come from the server snap only (07 §6.4) | Postgres geometry.landmark, geometry.landmark_history | — |
| DS-09 | Contour | Kernel value | Geometry Engine | {points: float64[k,3], closed: bool, plane{point, normal}, source_edges: int64[k] (edge keys), orientation: ccw about normal} | closed ⇒ first ≠ last point stored once; points lie on the plane within float64 rounding | Transient (measurement provenance stores plane + contour sha) | — |
| DS-10 | MeasurementDefinition | Versioned configuration record | Domain | {id, version, name_ru, formula_type ∈ {CI, CVA, CVAI_min_denominator, CVAI_max_denominator, HC} (proposed per OQ-FS-02), formula_text, plane_rule, diagonal_angle_deg, contour_selection_rule, diagonal_centre_rule, angle_reference_axis (proposed per OQ-FS-03), frame_definition_id, unit, source_ref, created_by/at} | Immutable once published; values reference (id, version) (FR-041) | Postgres governance.measurement_definition (inside config version) | config/1 section |
| DS-11 | MeasurementValue | Persistent record | Domain | {measurement_set_id, name, value: float64, unit, definition_id, definition_version, plane{…}, frame_id, computed_flag, provenance_class ∈ DATA-13 enum, synthetic_contact: bool, config_version} | No value without definition id+version (INV-05, SAF-06); no severity/threshold field exists (FR-045) | Postgres geometry.measurement_value | — |
| DS-12 | ZoneParams | Op parameters (zone.normal_falloff v1) | Domain/Geometry | {centre: DS-07 anchor, shape ∈ {circle, ellipse}, radius_mm \| (a_mm, b_mm, angle_deg, reference ∈ OQ-FS-10), magnitude_mm (signed; + = outward on positive), transition_mm, falloff: "smoothstep", category (clinic list), name} | No defaults; ranges checked against configured magnitude_ranges (SAF-07 confirmation) | Inside DS-04.params | op v1 |
| DS-13 | DeviationField | Kernel value + blob | Validation | {positive_sha, scan_sha, values: float32[n] (mm, + outward), mask: uint8[n] {0 valid, 1 boundary-masked, 2 closure-masked}, stats{global, per_zone}} | values finite; masked entries excluded from stats | Blob + Postgres geometry.validity_report summary | deviation/1 |
| DS-14 | DisplayMesh jude-mesh/1 | Binary payload | UI / Import-Export | 16-byte header "JMSH", u16 version, u16 flags, u32 nV, u32 nF; Float32[nV×3] positions mm (F_anat when available); Uint32[nF×3]; optional Float32[nV] scalar | display_only; never re-uploaded or used as kernel input | Blob (served via API with case scope) | jude-mesh/1 |
| DS-15 | ExportManifest jude-manifest/0.1 | JSON document | Import/Export | As 07 §6.7 + files[sha256, units], frame matrix, ops with effect statements (SAF-10), approval binding, reimport_check, software build, scope statement | Validates against published JSON Schema (INT-05); file sha equals STL sha | Blob + export record | jude-manifest/0.1 (TD-01 format still an assumption, OQ-FS-23) |
| DS-16 | ConfigDocument config/1 | Versioned JSON document | Domain/Data | Sections of 07 §5.4 (+ snap limit key if OQ-FS-14 accepts) ; every clinical/production key starts NOT_SET; test_only flag | Published versions immutable; diff + diff_sha per publication; test_only cannot be published to production (FN-CFG-07) | Postgres governance.config_version | config/1 |
| DS-17 | Job | Persistent record | Application | {id, type, status ∈ {queued, running, succeeded, failed}, payload{inputs[sha], params, requested_by, idempotency_key}, result jsonb, error_code, attempts, lease_until, heartbeat_at, created_at, finished_at, worker_id} | Claimed with FOR UPDATE SKIP LOCKED; retries only for idempotent types; release step of export never retried (07 §6.6) | Postgres ops.job | job/1 |
| DS-18 | AuditEvent | Append-only record | Security and Audit | core (hashed): {seq, type, user_id, role, object_type, object_id, object_version, case_id, at_utc, prev_hash, hash}; erasable: {summary_before, summary_after} (separate column/table, OQ-FS-07 recommendation) | INSERT-only DB role; chain verifies (ALG-58); no mesh data, no secrets | Postgres audit.audit_event (+ audit.audit_summary) | audit/1 |
| DS-19 | Artifact / BlobRef | Persistent record | Data | {sha256, kind ∈ {scan_original, scan_mm, scan_prepared, positive, display_lod, deviation_field, export_stl, manifest, report_pdf, prescription_file, integrity_report}, case_id, parent_shas[], frame, units, stats jsonb, lib_versions jsonb, display_only, bucket, size_bytes, created_at} | Immutable (INV-02); every artifact belongs to exactly one case (INV-01); prescription files in a separate bucket | Postgres data.artifact + Storage object at <bucket>/<sha[0:2]>/<sha> | — |
| DS-20 | ApprovalRecord | Persistent record | Domain/Validation | DATA-05: {design_version_id, geometry_sha, params_sha, scan_sha, measurement_set_id (OQ-FS-04), prescription_sha, checklist_version + answers, config_version + controlled-section last change, self_approval, statement_text (verbatim), approver_id, at_utc} | geometry_sha = version.geometry_sha at approval (INV-04); no approval without prescription_sha (FR-182) | Postgres governance.approval | — |
| DS-21 | ExportRecord | Persistent record | Import/Export | {id, design_version_id, approval_id, stl_sha, manifest_sha, export_frame matrix, reimport{passed, max_dev_mm, tolerance_mm}, released: bool, created_by/at, downloads[] (read events in audit)} | released ⇒ reimport.passed ∧ stl_sha in manifest (FR-102/103) | Postgres governance.export | — |
| DS-22 | Case / Scan / Consent / Prescription (clinical metadata) | Persistent records | Data (clinical zone) | case{case_id "J-"+8 Crockford base32, clinic_ref, status, archived}; consent_ref{case_id, reference, scope}; prescription{case_id, file_sha (prescription bucket), file_name, mime, size, attached_by/at}; scan_metadata{device, software+version, operator, date\|unknown, cap, posture, attempts, locked} | No direct identifiers in DB fields (DATA-10); prescription file is the only directly identifying object (R-40) — never parsed | Postgres clinical.* ; prescription bytes in bucket "prescriptions" | — |
| DS-23 | DesignVersion | Persistent record | Domain | {id, design_id, number, parent_id, status (07 §8.1), scan_sha, frame_id, config_version, template_ref, params_sha, geometry_sha, kernel_version, kernel_image_digest, created_by/at} | Saved ⇒ immutable except status transitions (INV-03); state machine FN-REV-06 | Postgres geometry.design_version | — |
| DS-24 | ErrorResponse | API payload | Application | {error: code (RTM v0.3 catalogue, OQ-FS-06), http_status, message_ru, gates: [{code, detail, link}], correlation_id} | Codes stable across versions; UI renders gate lists from it (FN-UIX-03) | — | error/1 |
| DS-25 | ValidityReport | JSON document | Validation | {geometry_sha, kernel_version, checks: [{id, label_ru ("геометрическая проверка"), passed, value}], passed} | Bound to geometry_sha; label wording per FR-082 | Postgres geometry.validity_report | validity/1 |

## 2. Interfaces

| ID | Interface | Mechanism | Between | Contract | Versioning |
|---|---|---|---|---|---|
| IF-01 | REST API (browser ↔ C3) | HTTPS JSON; OpenAPI 3.1 generated from FastAPI is the contract of record; generated TS client (openapi-typescript) | UI Layer → Application Layer | Path prefix /api/v1; Idempotency-Key on mutations; If-Match on versioned resources; 202 + job_id for long work; DS-24 errors | URI major version (/v1); additive changes only within v1; breaking change → /v2 with overlap period |
| IF-02 | Job contract (C3 ↔ C4 via ops.job) | Rows in Postgres; worker claims with SKIP LOCKED; results written back; completion handler in C3 transaction | Application Layer ↔ Geometry Engine | DS-17 payload: input shas + validated params; result: DS-05 summary + output shas | job/1 schema; job type names versioned (e.g. regenerate.v1) |
| IF-03 | Kernel operation contract | In-process Python call inside the worker: run(OpSpec, inputs: dict[str, DS-01], params) → DS-05; pure, no I/O, no clock, no randomness | Geometry Engine (internal) | Inputs/outputs typed arrays; params validated by JSON Schema before call | op_version per op; kernel_version (semver) + container image digest recorded per result |
| IF-04 | BlobStore interface | put(bytes, kind, case_id) → sha256; get(sha256) → bytes; exists(sha256); purge(sha256, credential) only for erasure procedure | Data Layer | Content addressing; no overwrite; app role has no delete; adapters: Supabase Storage (S3 protocol), filesystem (tests) | Interface v1; adapter version recorded in deployment record |
| IF-05 | Display payload jude-mesh/1 | GET /api/v1/blobs/{sha} (case-scoped) → DS-14 | Import/Export → UI Layer | Binary little-endian | Header version field |
| IF-06 | Export hand-off | Download of released STL + manifest JSON (file-based, DEC-009/013) | Import/Export → production (outside Jude) | DS-15 + binary STL mm | jude-manifest/0.1 schema id |
| IF-07 | Configuration schema | config/1 JSON Schema (sections, NOT_SET semantics) | Domain ↔ Data | DS-16 | Schema version in document; migration functions for config/1 → config/2 |
| IF-08 | Audit append (internal) | audit.append(session, event_core, summary) within the caller transaction | Security and Audit (used by all) | DS-18 | audit/1 |
| IF-09 | Permission table | permissions.yaml: role × action × condition; drives FastAPI dependencies and VER-12 tests | Security and Audit | YAML + JSON Schema | Versioned with code; schema checked at start-up |
| IF-10 | Report renderer | render_report(inputs: stored records, template_version) → PDF bytes (WeasyPrint) + PNG views (ALG-60) | Application (worker) | HTML template + values | Template version recorded in report record |
| IF-11 | Scan import (file intake) | POST /api/v1/cases/{id}/scans multipart → original blob + parse job | UI → Import/Export | STL/OBJ/PLY bytes ≤ S MB | — |
| IF-12 | CI oracle interface | Oracle runner (separate container, GPL tools) reads fixtures + kernel outputs, writes comparison JSON | Build/CI | Fixture files + JSON | Fixture set version |

### 2.1 Endpoint catalogue

The MVP endpoint list of 07 §6.2 rows 1–31 plus CN-11 additions (consent reference, real-data gate, prescription endpoints, read-access audit) is adopted under the `/api/v1` prefix. Error codes follow RTM v0.3 (PRESCRIPTION_MISSING, ZONE_OVERLAP_NOT_ALLOWED) once OQ-FS-06 is signed. Prescription endpoint permissions and size limit remain open (OQ-FS-26).

### 2.2 Input/output contracts per function

Every catalogue row lists its input contract, output contract and interfaces in FUNCTION_COMPONENT_MAPPING_v1.0.csv (columns input_contract, output_contract, interfaces) and in the 22-field specifications.

## 3. Data architecture

### 3.1 Zones (clinical metadata separated from geometry)

| Zone | Name | Tables | Buckets | Access | Retention | Encryption |
|---|---|---|---|---|---|---|
| Z-CLIN | Clinical metadata zone | clinical.case, clinical.consent_ref, clinical.prescription, clinical.scan_metadata, clinical.cohort (conditional) | Bucket "prescriptions" (directly identifying file, R-40) | Technician + clinic admin per permission table; every read logged (SEC-15); downloads controlled (SEC-16) | Clinic contract (SD-06); erasure procedure FN-CAS-08 (OQ-FS-07) | Platform encryption at rest (SD-08, A-SRC-06/07 extracts only — MA-05) |
| Z-GEO | Geometry zone (pseudonymised personal health data, DEC-019) | geometry.scan, geometry.landmark*, geometry.frame, geometry.measurement_*, geometry.design*, geometry.operation, geometry.validity_report, data.artifact | Buckets "scans" (originals), "artifacts" (derived arrays, LOD, fields) | Case-scoped reads via API only; SHAs are not capabilities (FR-002) | As case; derived artifacts purged with case | As above |
| Z-GOV | Governance and records zone | governance.user, session, role_grant, config_version, measurement_definition, frame_definition, approval, rejection, export, report, template* | Buckets "exports", "reports" | Role-restricted; approvals/exports technician-only (FR-130) | As case for case-linked rows; accounts per SEC-19 | As above |
| Z-AUD | Audit zone | audit.audit_event (core, hashed), audit.audit_summary (erasable), audit.chain_head | — | INSERT-only role for app; SELECT for admin views; no UPDATE/DELETE grants | Not deleted by app; summaries erasable (OQ-FS-07) | As above |
| Z-OPS | Operations zone | ops.job, ops.idempotency_key, ops.backup_record, ops.blob_verification | — | Service roles (api, worker) | Rotated per policy (TBD) | As above |

### 3.2 Entity coverage requested by the brief

| Brief item | Structures | Zone |
|---|---|---|
| Patient case metadata | DS-22 case, consent_ref, scan_metadata (pseudonymous; no direct identifiers) | Z-CLIN |
| Scan files | DS-19 kind=scan_original (bytes, SHA-256, never modified), DS-22 scan metadata | Z-GEO / bucket scans |
| Mesh objects | DS-01 in blobs jude-arr/1; DS-19 artifact lineage (parent_shas) | Z-GEO / bucket artifacts |
| Coordinate systems | DS-06 Transform4 with from/to/det | Z-GEO |
| Landmarks | DS-07, DS-08 (+ append-only history) | Z-GEO |
| Measurements | DS-10 definitions (versioned), DS-11 values with provenance | Z-GOV (definitions) / Z-GEO (values) |
| Helmet geometry | DS-23 design versions, DS-04 op-log, positive artifacts (DS-01) | Z-GEO |
| Correction and relief regions | DS-12 ZoneParams inside DS-04; category list in DS-16 | Z-GEO / Z-GOV |
| Validation results | DS-02, DS-25, DS-13 | Z-GEO |
| Design versions | DS-23 (immutable after save), state machine FN-REV-06 | Z-GEO |
| Approval records | DS-20 | Z-GOV |
| Manufacturing exports | DS-21, DS-15, STL blobs | Z-GOV / bucket exports |

### 3.3 Confidentiality, access, audit and retention

- Classification: scans are pseudonymised personal health data (DEC-019); the prescription file contains direct identifiers (R-40).
- Access: server-side permission table (IF-09), case scope on every object and blob; SHAs are not capabilities; no browser access to tables or buckets (TD-13).
- Audit: every state change in-transaction (ADR-012); every read of scans, prescriptions, exports, reports and audit CSV logged (SEC-15).
- Retention and erasure: per clinic contract (SD-06); erasure path blocked until OQ-FS-07 (privileged purge credential + erasable audit summaries).
- Encryption at rest: Supabase platform statement (SD-08; full read pending MA-05); separate Storage backup must be encrypted (SEC-13).
- Backups: database (platform) + **separate** Storage backup (platform DB backups exclude Storage objects, T-SRC-08); restore drill restores both and re-verifies SHAs and the audit chain (TC-SEC-08).

### 3.4 Schema versioning

- DB: forward-only migrations (Alembic); migration test on empty DB per release (TC-DATA-*).
- Documents: schema id inside each document (config/1, integrity/1, validity/1, deviation/1, audit/1, job/1, jude-manifest/0.1, jude-arr/1, jude-mesh/1).
- Kernel: op_version per op; kernel_version + container image digest per DesignVersion (reproduction of old approvals, TQ-15).
