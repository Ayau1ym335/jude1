# Decision Record — Implementation Decisions IDR-01…IDR-38

| Field | Value |
|---|---|
| Document | DECISION_RECORD_2026-11-17.md |
| Task | XC-FND-01 — Ratify Implementation Decision Record |
| Source | IMPLEMENTATION_PLAN_v1.1.md §6 (decisions prepared under the product owner's delegation, session 2026-11-15; IDR-37 and IDR-38 added 2026-11-17 by CN-2026-11-17) |
| Ratified by | Ayau — engineering lead (CTO) and product owner (both roles held by the same person) |
| Date | 2026-11-17 |
| Form of approval | Written statement in the planning session on 2026-11-17: "я принимаю все" (accept all) in reply to the list of IDR-01…IDR-38. Copy this file into `docs/adr/` and commit it to give the approval a repository timestamp. |
| Result | 38 of 38 IDR approved: 33 Approved, 4 Approved-provisional (IDR-03, IDR-20, IDR-25, IDR-29), 1 Approved-conditional (IDR-33) |

## 1. Meaning of the statuses

| Status | Meaning |
|---|---|
| Approved | Binding for implementation. Change only through a new ADR. |
| Approved-provisional | Binding as a default for implementation. The clinic technician or the engineering lead may change the value later through a versioned op, a definition field or a configuration change, without changing the approval chain. |
| Approved-conditional | Binding, with a named evidence gate. IDR-33: library lock-in (TD-02, TD-03, TD-05, TD-11, ADR-002) is confirmed or reversed at milestone M1 exit on experiments X-01, X-02, X-06, X-08 (task XC-EXP-LOCK). |

## 2. Effects of the ratification

1. Blocking functional questions OQ-FS-01…04, -06, -07, -08 are closed by IDR-01…07 (see the "Closes" column below).
2. Technical questions listed in the "Closes" column are closed; technical decisions TD-01…TD-26 are Approved for implementation under IDR-33, except those named in IDR-33 as locked in at M1 exit (Conditional).
3. Tasks previously gated by XC-FND-01 are released for implementation, subject to their other dependencies in TASK_DEPENDENCY_MATRIX_v1.1.csv.
4. The decisions are about software and geometry only. None of them sets a clinical rule, threshold, correction magnitude or regulatory status (STK-05, SAF-02, DEC-029).

## 3. Decisions

| ID | Closes | Decision | Rev. | Status | Affects |
|---|---|---|---|---|---|
| IDR-01 | OQ-FS-01, TD-07, GAP-A03/C06 | Positive closure is a **pinned terminal operation**: recorded in the op list, always evaluated last, position not editable; new design starts with 0 ops; BL-017 wording corrected | M | Approved | FN-KOP-06, FN-KRP-01, FN-DES-01/02 |
| IDR-02 | OQ-FS-02, GAP-A05 | Measurement formula = **enumerated formula type** {CI, CVA, CVAI_min_denominator, CVAI_max_denominator, HC} + parameters; DATA-02 "formula expression" stores the type code and a human-readable string | M | Approved | FN-CFG-05, FN-MEA-01, DS-10 |
| IDR-03 | OQ-FS-03, TQ-18, GAP-M11/M12 | Definitions gain three fields: `contour_selection_rule` {enclosing_origin_projection, largest_perimeter, technician_pick}, `diagonal_centre_rule` {origin_projection, contour_area_centroid}, `angle_reference_axis` {AP, ML}; kernel supports all options; the two shipped presets (30°, 40°, DEC-027) carry enclosing_origin_projection / origin_projection / AP (provisional, technician-editable per definition); non-convex diagonals use the **outermost** intersections | R | Approved-provisional | FN-KMS-02/04, FN-CFG-05/06, FN-MEA-01 |
| IDR-04 | OQ-FS-04, GAP-M16 | Approval binds **one measurement set explicitly selected** by the technician from the current (non-superseded) sets on the design's frame; no pre-selection | R | Approved | FN-REV-04, DS-20 |
| IDR-05 | OQ-FS-06, GAP-C02, TD-22 | Error catalogue = **RTM v0.3 codes** (PRESCRIPTION_MISSING, ZONE_OVERLAP_NOT_ALLOWED; CN-11 names retired); catalogue `error/1` frozen at M0 exit; `/api/v1` | R | Approved | FN-API-02, XC-FND-06 |
| IDR-06 | OQ-FS-07, GAP-C04 | Audit hash covers only the **non-erasable core** (seq, type, user/role, object refs, time, prev_hash); summaries live in an erasable table outside the hash. Blob erasure via a **separate privileged purge credential** held by the engineering lead, usable only by the FN-CAS-08 procedure, every use audited | H | Approved | FN-AUD-01, FN-BLB-04, FN-CAS-08, DS-18 |
| IDR-07 | OQ-FS-08, TQ-02, TQ-03, TQ-20, TD-13 | **Deployment:** Docker Compose on one Linux x86-64 host in the same region as the Supabase project (provider chosen in M1 by: region match, Docker, rlimits/seccomp, backups); C0 = Caddy reverse proxy (TLS ≥ 1.2, same-origin `/api`), Next.js, FastAPI, worker pool. **Data:** direct Postgres connections with roles app_rw / worker_rw / audit_append (INSERT-only) / admin_ro; Storage only through IF-04 with service credentials. **Backup:** platform DB backup + **separate daily encrypted Storage backup with restic** to a different provider/account. **Sandbox:** parse in a child process with rlimits, read-only FS, no network, non-root, Docker default seccomp. **Fallback if X-07 shows the app credential can overwrite/delete:** IF-04 enforces no-overwrite (exists-check, content addressing) and the bucket policy denies delete; if a policy cannot deny delete, blobs move to S3-compatible storage with object lock | M | Approved | XC-FND-07/08/09, FN-BLB-*, FN-OPS-05 |
| IDR-08 | TQ-04, TD-14 | **Own session auth** (argon2id, server-side sessions, SD-01 lockout, SD-02 idle timeout, CSRF token); Supabase Auth not used | M | Approved | FN-IAM-* |
| IDR-09 | TQ-09, X-08 | **Python 3.12**, linux/amd64 only for MVP images; Node.js active LTS at M0, pinned; package managers **uv** (Python) and **pnpm** (JS); versions of LIBRARY_COMPARISON_v1.0 pinned in lockfiles and re-checked by X-08 | R | Approved | All |
| IDR-10 | TQ-05, TQ-11, TD-02, TD-03, TD-05 | **Lean kernel:** numpy/scipy + own algorithms; **one own deterministic BVH (numba, fastmath off, parallel off)** shared by self-intersection, closest point, ray casting and signed distance; own port of Shewchuk predicates; libigl/trimesh/CGAL/PyMeshLab are CI oracles only. Fallbacks: numba fails X-06 → C++ extension (nanobind) for the same inner loops; own BVH fails X-01 performance → libigl (MPL-2.0) for closest point | H | Approved | XC-SHR-01/02, FN-KVL-05, FN-KAN-01, FN-KCP-01 |
| IDR-11 | TQ-06 | Windowed-sinc smoothing **implemented in-house** (VTK not shipped) | R | Approved | FN-KOP-12 |
| IDR-12 | TQ-07, TD-11, OQ-FS-17 (part) | Display LOD: **fast-simplification** (MIT) if deterministic in X-01, else meshoptimizer; recorded op cleanup.decimate (Should): own constrained QEM | R | Approved | FN-KOP-03/04 |
| IDR-13 | TQ-08, TD-12 | Cap triangulation: **own exact ear clipping** (orient2d); mapbox-earcut as test oracle | R | Approved | FN-KOP-06 |
| IDR-14 | TQ-10, OQ-FS-24, TD-18 | Deviation image for the PDF by **own orthographic z-buffer rasteriser**; PDF by WeasyPrint | R | Approved | FN-RPT-02 |
| IDR-15 | TQ-25 | Blob container **jude-arr/1** (own minimal header, little-endian raw arrays, no pickle, no zip timestamps) | M | Approved | XC-FND-12, DS-01 |
| IDR-16 | TQ-21, TQ-23 | trimesh 5.x oracle-only; matplotlib only in analytics notebooks, never shipped | R | Approved | FN-OPS-07, FN-OPS-09 |
| IDR-17 | TQ-17 | OBJ polygons k > 3: fan triangulation if convex in the Newell plane, exact ear clipping otherwise | R | Approved | FN-KIO-03 |
| IDR-18 | TQ-26, TQ-19 | Guard: normal-flip threshold 0 with exact orient3d fallback near 0; transition width T ≥ 0 allowed (T = 0 accepted only if the guard passes); clinic ranges via magnitude_ranges (SAF-07) | R | Approved | FN-KOP-10/13 |
| IDR-19 | TQ-15, TQ-16 | Kernel container images retained for the case retention period; no cross-host determinism fallback is pre-approved — decided only on BM-03 evidence | R | Approved | FN-KRP-01, FN-OPS-04 |
| IDR-20 | OQ-FS-09, -10, -11, -19, -20 | **Revised by CN-2026-11-17:** the zone profile is an op parameter (FN-KOP-15: plateau, peak or custom monotone curve) and zones may be free-form contours (FN-KOP-14); plateau + smoothstep remains the default preset. Other provisional geometric defaults (technician may change by op_version): ellipse orientation from the projected vertical axis (fallback A-P axis); angle-weighted vertex normals; smoothing blend smoothstep; global length = whole-surface extent along the axis; circumference = contour perimeter at the chosen level | M | Approved-provisional | FN-KOP-05/08/09/10/12 |
| IDR-21 | OQ-FS-12 | Closure (wall/cap) and boundary-masked vertices excluded from deviation statistics and drawn neutral grey | R | Approved | FN-KCP-01 |
| IDR-22 | OQ-FS-13 | Degenerate faces = **exact** collinearity (orient predicates) or repeated index, i.e. ε_area = 0 under exact arithmetic; slivers reported as a diagnostic (min angle) only | R | Approved | FN-KVL-02 |
| IDR-23 | OQ-FS-14, GAP-M02 | Landmark snap-distance limit = engineering constant 2 × max LOD deviation reported by FN-KOP-04 (not a clinical key) | R | Approved | FN-ANA-02, FN-KAN-01 |
| IDR-24 | OQ-FS-15, -21, -22 | No unit proposal (all four bounding boxes shown); "newer scan" = upload time (acquisition date shown as information); plausible size compares sorted extents at import | R | Approved | FN-SCN-04/08, FN-REV-04, FN-EXP-01 |
| IDR-25 | OQ-FS-16, -17, -28, TQ-12 | Hole filling only on technician-selected loops ≤ P; Liepa triangulation + refinement, fairing behind a flag; n_max set from BM-02 statistics (until then hole filling runs only in test configurations); cleanup.decimate kept as a recorded Should op enabled only when a scan exceeds N | R | Approved-provisional | FN-KOP-02/03, FN-SCN-11 |
| IDR-26 | OQ-FS-18 | Sector coverage = ray-hit fraction ≥ c_min; c_min is clinic configuration | R | Approved | FN-KAN-03 |
| IDR-27 | OQ-FS-23 | Manifest format jude-manifest/0.1 JSON + published JSON Schema | R | Approved | FN-KEX-01/02 |
| IDR-28 | OQ-FS-25, OQ-FS-27 | Add two requirements in RTM v0.4: case list/search; warning for measurements over synthetic surface | R | Approved | FN-CAS-02, FN-KMS-06 |
| IDR-29 | OQ-FS-26, GAP-M18 | Prescription: technician attaches; technician and clinic admin may view/download (every access logged, SEC-15/16); accepted types per FR-164; **maximum file size 20 MB** (provisional product limit for scanned multi-page PDFs) | R | Approved-provisional | FN-CAS-06/07 |
| IDR-30 | OQ-FS-37, GAP-M08 | Scan winding: recorded op `normalise_orientation` proposed to the technician when inconsistency or an inward hint is found (no silent repair); closure faces oriented automatically by construction | R | Approved | FN-KVL-04, FN-KOP-05/06 |
| IDR-31 | OQ-FS-38, GAP-C10 | M1 **walking skeleton** on a synthetic phantom with a test-only frame fixture (flag test_only, cannot reach production — FN-CFG-07); product milestones follow the dependency order (anatomy before design) | R | Approved | XC-WSK-01 |
| IDR-32 | OQ-FS-05, -33, -35, -36 | RTM v0.3 governs configuration approval (backlog BL-030/BL-115 texts corrected); denoising, reconstruction, remeshing, shell, wall thickness and 3MF stay out of MVP; BL-112 retired; DATA-18 cohort descriptors not built in MVP | R | Approved | MVP_SCOPE §6–7 |
| IDR-33 | TQ-01, OQ-FS-30 | FS v1.0 and TD v1.0 set approved **for implementation** (not Baselined); library lock-in (TD-02/03/05/11, ADR-002) signed at M1 exit on X-01/X-02/X-06/X-08 evidence (XC-EXP-LOCK) | M | Approved-conditional | All |
| IDR-34 | — (tooling) | Monorepo on GitHub; GitHub Actions; trunk-based development with short-lived branches; Conventional Commits with task-ID trailer; CODEOWNERS; Dependabot; SQLAlchemy 2 + Alembic + psycopg 3; Caddy; restic | R | Approved | DEVELOPMENT_STANDARDS, REPOSITORY_STRUCTURE |
| IDR-35 | Scope | 7 Should functions promoted to Core; 19 Should functions ordered by cut line; 8 Next, 5 Deferred | R | Approved | MVP_SCOPE |
| IDR-36 | Planning | 2-week sprints; focus factor 0.7; estimates in ideal pd with three points; re-estimate at every milestone exit; commitments at P80 | R | Approved | DEVELOPMENT_ROADMAP |
| IDR-37 | CN-2026-11-17 | Adopt change notice CN-2026-11-17: CH-01…CH-05 into MVP-Core, CH-06…CH-12 into MVP-Should (CH-12 decided by IDR-38), CH-13 to v1.1; milestone M4 split into M4a/M4b; XC-PLT-13 observation of a helmet session in M0 gates all new functions | R | Approved | MVP_SCOPE v1.1, WBS v1.1 |
| IDR-38 | OD-09, DEC-028 (amended), CH-12 | Whole-surface smoothing (Rodin4D "Complete Smoothing") allowed as an explicit, recorded, replayable op: smooth.windowed_sinc with region = whole scan-origin surface; local smoothing stays primary; no default parameters (technician enters iterations/pass-band); closure faces excluded; max/RMS deviation shown before save; measurements refuse smoothed artifacts (FR-179) | R | Approved | TSK-KOP-12-KG (MVP-Should, cut-line rank 5) |

## 4. Not covered by this record (remain open)

| ID | Decision | Owner |
|---|---|---|
| OD-01 | Clinic configuration values (landmark set, frame rule, gate thresholds, coverage sectors, c_min, base convention, export frame, checklist, magnitude ranges) | Clinic technician |
| OD-02 | Pilot success thresholds for design time and measurement agreement | Clinic |
| OD-03 | Pilot-entry values N, S, face cap, LOD budget, n_max, time budgets | Engineering lead + clinic IT |
| OD-04 | Team composition and start date | Product owner |
| OD-05 | Hosting provider for the container host (criteria fixed in IDR-07) | Engineering lead |
| OD-06 | Accept cross-host determinism fallback if BM-03 fails | Engineering lead + QA lead |
| OD-07 | Regulatory and legal questions RQ-01…15, LQ-03 | Experts, when the owner decides |
| OD-08 | Baselining of the RTM (MA-01 spot-check, independent re-audit) | Named reviewer |

OD-09 was closed on 2026-11-17 by IDR-38.

## 5. Change rule

A change to any decision above needs a new ADR in `docs/adr/` that names the IDR it replaces, states the reversibility class (R/M/H) and lists the affected WBS tasks. IDs are never reused.

## 6. Approval record

| Role | Name | Date | Statement |
|---|---|---|---|
| Engineering lead (EL) | Ayau | 2026-11-17 | Accepts IDR-01…IDR-38 |
| Product owner (PO) | Ayau | 2026-11-17 | Accepts IDR-01…IDR-38 |
