# Implementation Plan v1.1 — Jude cranial remolding helmet (CRO/CRH) design software

| Field | Value |
|---|---|
| Document | IMPLEMENTATION_PLAN_v1.1.md |
| Version / date | v1.1 · 2026-11-17 — applies change notice CN-2026-11-17 (CAD workspace parity with Rodin4D, approved by the product owner 2026-11-17); supersedes v1.0 of 2026-11-15 |
| Roles | Technical project manager, software architect, lead developer (this plan) |
| Status | Decisions ratified 2026-11-17. Every decision in §6 was prepared under the product owner's explicit delegation in the session of 2026-11-15 ("all questions and the list of decisions are entrusted to you — choose the optimal options") and accepted in full by the engineering lead and product owner on 2026-11-17 (task XC-FND-01 done; DECISION_RECORD_2026-11-17.md). |
| Baseline used | FUNCTIONAL_SPECIFICATION_v1.0 · FUNCTION_CATALOG_v1.0 (226 rows) · FUNCTION_REQUIREMENT_TRACEABILITY_v1.0 · TECHNICAL_DESIGN_v1.0 + FUNCTION_TECHNICAL_SPECIFICATIONS / CAD_GEOMETRY_ENGINE_DESIGN / DATA_STRUCTURES_AND_INTERFACES / PERFORMANCE_REQUIREMENTS / TECHNICAL_DECISIONS / TECHNICAL_OPEN_QUESTIONS v1.0 · ALGORITHM_CATALOG_v1.0 (61) · LIBRARY_COMPARISON_v1.0 (40) · FUNCTION_COMPONENT_MAPPING_v1.0 · GEOMETRY_TESTING_STRATEGY_v1.0 · RTM v0.3 (200) · 09a_MVP_BACKLOG v0.3 (107) · DR-2026-11-12 |
| Boundary | Software and geometric correctness only. No clinical rule, threshold, correction magnitude or regulatory status is set here (STK-05, SAF-02, DEC-029). Passing the planned tests is not evidence of clinical safety, fit or effectiveness (FR-082). |
| Calendar | **No calendar dates.** Effort is in ideal person-days (pd); durations are in working days (WD) and 2-week sprints for named team scenarios. Dates follow only when team size and start date are fixed (§8.5). |

## 1. Summary

| Item | Result |
|---|---|
| MVP scope | 157 functions: **132 MVP-Core**, **25 MVP-Should** (cut line ordered); 9 functions Next (v1.1); 5 Deferred — MVP_SCOPE_v1.1 (11 functions added by CN-2026-11-17) |
| Requirement coverage | 185/185 MVP requirements (174 of RTM v0.3 + 11 proposed FR-183…FR-193) covered by ≥ 1 task; MVP-Core alone covers 171/185 (the other 14 are *Should* requirements) |
| Work breakdown | 15 epics · 31 modules · 338 scheduled tasks (+ 14 outline rows) · 67 subtasks (= all MVP subfunctions) — WORK_BREAKDOWN_STRUCTURE_v1.1.csv |
| Dependencies | 1,391 finish-to-start edges, acyclic, milestone-consistent (0 violations) — TASK_DEPENDENCY_MATRIX_v1.1.csv |
| Effort (MVP-Core + Should) | Optimistic **443** · most likely **758** · pessimistic **1,317** · PERT **798** pd. Monte Carlo with correlated bias: P10 821 · **P50 915** · **P80 1,009** · P90 1,070 pd (v1.0: ML 678, P80 900) |
| MVP-Core only | ML 665 · PERT 701 pd |
| Duration (reference team, 4 FTE) | Plan value 413 WD (≈ 42 sprints); P50 492 WD (50 sprints); P80 546 WD (55 sprints) |
| Bottleneck | Resource-bound, not dependency-bound: unconstrained critical path is 116 WD; kernel carries ≈ 216 pd and backend ≈ 204 pd |
| Decisions | 38 implementation decisions (IDR-01…IDR-38; IDR-20 revised and DEC-028 amended by CN-2026-11-17) close all 7 blocking functional questions and 26 technical questions that can be closed without external data |
| External gates | 7 (EXT-01…EXT-07): VER-22 inspection, clinic IT inventory, BM evidence for NFR values, clinic configuration values, clinic files, Rodin4D Neo access, legal licence review |
| Change notice | CN-2026-11-17: 16 changes CH-01…CH-16 from observing Rodin4D at the clinic — free-form zones, profile editor, symmetric zones, live design metrics, overlay, 2D sections, tape measure, orientation fine-tuning; +79.9 pd ML (+11.8 %) |
| Readiness for Claude Code | **Ready to start M0–M1 (synthetic data only) — conditional** only on creating the repository (§11); decision record XC-FND-01 ratified 2026-11-17 |

## 2. Baseline check

| Check | Result | Consequence |
|---|---|---|
| Function IDs present in WBS | 159 catalogue functions + 12 proposed by CN-2026-11-17 (FN-KOP-14…18, FN-DES-08, FN-UIX-07…09, FN-MEA-05, FN-ANA-06, FN-PMV-13) + 67 subfunctions; 157 MVP functions each have ≥ 1 task; 67/67 MVP subfunctions mapped | FUNCTION_CATALOG v1.1 to be issued (XC-FND-10) |
| Requirement IDs in WBS exist in RTM v0.3 | 0 unknown IDs; 11 proposed IDs FR-183…FR-193 pending RTM v0.4 | XC-FND-10 adds the rows |
| Blocking functional questions | OQ-FS-01…04, -06, -07, -08 | Closed by IDR-01…07 (pending ratification) |
| FS v1.0 / TD v1.0 approval record | Not found (TQ-01) | IDR-33: approved for implementation; ratified 2026-11-17 (XC-FND-01) |
| RTM status | Owner-approved, not Baselined (MA-01 literature spot-check and independent re-audit open) | Does not block software work; tracked as OD-08 |
| Backlog v0.3 vs dependency order | Conflicts GAP-C10 (design before anatomy) | IDR-31: M1 walking skeleton with a test-only frame; product milestones follow dependency order |
| Platform | Supabase chosen (SD-05); DB backups exclude Storage objects (T-SRC-08) | IDR-07 + XC-EXP-07 + separate encrypted Storage backup |

## 3. Planning approach and assumptions

| ID | Assumption / rule | Effect |
|---|---|---|
| PA-01 | Unit = ideal person-day (focused engineering day). Focus factor 0.7 converts to working days (meetings, review, context switching). | WD = pd ÷ (0.7 × FTE) |
| PA-02 | Three-point estimates per task (O/ML/P) from a calibrated table per task type and size (§5.2) with explicit overrides for hard items (self-intersection, closure, replay, viewer, design workspace). | Range reported, not a single number |
| PA-03 | Uncertainty model: 200 Monte Carlo runs, triangular per task **and** one correlated bias factor per run ~ Tri(0.9, 1.0, 1.4) applied to all tasks (estimation bias is systemic in novel geometry work). | P50/P80 used for commitments |
| PA-04 | Sprint = 10 working days; capacity per FTE per sprint = 7 pd. | Sprint counts in §8 and the roadmap |
| PA-05 | Team composition is not decided; three scenarios are planned (S1 Lean 2.5 FTE, S2 Reference 4 FTE, S3 Balanced 6 FTE). External roles (engineering lead, privacy specialist, clinic, product owner) are modelled as 2 × 0.5 FTE. | No calendar dates (§8.5) |
| PA-06 | Each task is executed by one person; a geometric-verification task (TT-V) is executed by a QA engineer who did not write the kernel task (independence, GTS §3). | Scheduler assigns pools |
| PA-07 | Every task's effort includes its own unit tests, code review and documentation; stabilisation reserve = 10 % (5–20 %) of each pool's Core effort per milestone (XC-STB-*). | No hidden test effort |
| PA-08 | Real clinic scans are used only after the VER-22 record exists (SEC-17); everything before uses synthetic fixtures. | Gate EXT-01 |
| PA-09 | Clinical/production values are never defaulted in code; the software is built and tested with every such key NOT_SET and test-only configurations (DEC-029, SAF-02). | Pilot needs EXT-04 |

## 4. MVP scope (summary)

See MVP_SCOPE_v1.1.md. Inclusion criteria IC-01…05, exclusion criteria EC-01…06, promotions (IDR-35), cut line of 19 Should functions, Next (v1.1) and Deferred items, soft dependencies removed from the Core path.

## 5. Work breakdown structure

### 5.1 Hierarchy and identifiers

| Level | ID pattern | Count | Example |
|---|---|---|---|
| Epic | EP-01 … EP-15 | 15 | EP-05 Geometry kernel — I/O, validation, frames, replay, export, shared primitives |
| Module | MOD-<code> (26 catalogue modules + XFND, XSHR, XEXP, XPLT, XSTB) | 31 | MOD-KVL |
| Feature | catalogue Function ID (FN-…) or FEAT-<module> for enabler groups | 171 + 5 | FN-KVL-05 |
| Task | TSK-<MOD>-<NN>-<T> for function tasks; XC-<GRP>-<NN> for enablers | 338 scheduled + 14 outline | TSK-KVL-05-K, XC-SHR-02 |
| Subtask | <task>.S<n> = catalogue subfunction | 67 | TSK-KVL-05-K.S1 → FN-KVL-05.1 |

Task type letter <T>: **K** kernel implementation · **V** geometric verification · **B** domain service + API · **U** UI · **J** background job · **A** synchronous service · **O** procedure + runbook · **C** CI/test tooling · **X** outline (not scheduled). `wbs_code` gives the numeric outline position (e.g. 5.2.5.1.1).

### 5.2 Task-type templates (referenced as TT-x in the WBS `description` column)

| Template | Scope of work | Standard deliverables | Standard tests | DoD |
|---|---|---|---|---|
| TT-K | Pure kernel function in `packages/kernel/src/jude_kernel/kNN_*`; contract IF-03 (arrays + explicit params in, OpResult out); no I/O, clock, randomness or global state; float64 mm; deterministic order; registry entry with op_version if it is an op; follows the cited ALG/TD | Module + registry entry + unit and property tests | UT-<FN>, PT-<FN> (+ catalogue TC IDs) | DoD-STD + DoD-K |
| TT-V | Independent verification of the K task on fixture sets (T1–T15) against analytic truth within DEC-025; invariants and edge cases of GTS §6; golden hashes; oracle comparison in the CI oracle container | `tests/geometry/kNN_*` + golden files + oracle report | GT-<FN>, RT-<FN>, ORC-<ALG> | DoD-STD + DoD-V |
| TT-B | Domain service, persistence (migration if needed), `/api/v1` endpoint(s), permission-table rows, audit events in the same transaction, DS-24 error codes | `services/api/.../domain/<mod>` + router + migration + permissions rows | UT-<FN>, IT-<FN>, VER-12 rows, VER-13 events | DoD-STD + DoD-B |
| TT-U | Russian UI using the generated OpenAPI client; gates rendered from DS-24 via FN-UIX-03; no client-side geometry decisions; wording lint clean | `apps/web/src/features/<mod>` + ru strings + component tests | CT-<FN>, E2E step in FN-OPS-08 | DoD-STD + DoD-U |
| TT-J | Worker job (job/1 payload, idempotency rule, kernel via IF-03); completion handler commits result + domain change + audit atomically (EH-JOB) | `services/worker/.../jobs/<mod>` + completion handler | UT-<FN>, IT-<FN> (incl. failure/retry) | DoD-STD + DoD-J |
| TT-A | Synchronous service or middleware with EH-API error mapping | `services/api/.../platform|domain/<mod>` | UT-<FN>, IT-<FN> | DoD-STD + DoD-A |
| TT-O | Procedure tooling + runbook; each step leaves an audit/record entry (EH-PROC) | `scripts/ops/` + `docs/runbooks/<FN>.md` + record template | OT-<FN> (staging dry run), IT-<FN> | DoD-STD + DoD-O |
| TT-C | CI/test tooling wired into the GTS §7 stage (EH-CI) | `.github/workflows` + `tools/` or `tests/` harness | CI-<FN> (seeded violation fails, clean tree passes) | DoD-STD + DoD-C |

Definitions of DoD-STD and DoD-K…DoD-P are in DEVELOPMENT_STANDARDS_v1.0 §11.

### 5.3 Codes used in the WBS

| Skill code | Meaning | Role code | Meaning |
|---|---|---|---|
| SK-KRN | Python 3.12, numpy/scipy, computational geometry | KE | Kernel (geometry) engineer |
| SK-ROB | Robust geometry: exact predicates, BVH, tie rules | BE | Backend engineer |
| SK-NUM | Numerical methods, sparse linear algebra, rasterisation | FE | Frontend engineer |
| SK-DET | Determinism, content-addressed caching | QA | QA / DevOps engineer |
| SK-BE | FastAPI, PostgreSQL/SQLAlchemy/Alembic, transactions | QAG | QA engineer (geometry), not the author of the K task |
| SK-FE | TypeScript, React/Next.js, Russian UI copy | EL | Engineering lead (CTO) |
| SK-3D | three.js, WebGL, Web Workers, three-mesh-bvh | PO | Product owner |
| SK-QA | pytest/hypothesis/Playwright | PS | Privacy specialist |
| SK-QAG | Geometry fixtures, tolerances, oracle tools | CT / CL / CP / CIT | Clinic technician / clinical lead / clinic production / clinic IT |
| SK-OPS | GitHub Actions, Docker, Linux hardening, Supabase, restic | RO | Requirements owner |
| SK-SEC | Threat modelling, OWASP ASVS, hash chains | | |
| SK-PRV | Privacy engineering, VER-22 evidence | | |
| SK-PDF | WeasyPrint, print CSS | | |
| SK-DOM | Domain role (decision, inspection, clinical input) | | |

### 5.4 Epics

| Epic | Name | Tasks | Opt | ML | Pess | PERT |
|---|---|---|---|---|---|---|
| EP-01 | Engineering foundation, decisions and environments | 12 | 23.5 | 41.0 | 66.0 | 42.3 |
| EP-02 | Platform services (identity, API conventions, audit, jobs, blob store) | 27 | 23.0 | 40.5 | 73.5 | 43.0 |
| EP-03 | Clinic configuration | 14 | 23.0 | 37.0 | 62.0 | 38.8 |
| EP-04 | Case and data governance | 15 | 11.0 | 20.0 | 38.0 | 21.5 |
| EP-05 | Geometry kernel — I/O, validation, frames, replay, export, shared primitives | 52 | 60.5 | 99.5 | 177.0 | 105.8 |
| EP-06 | Geometry kernel — anchors, measurement, design ops, comparison | 66 | 94.0 | 164.5 | 284.0 | 172.6 |
| EP-07 | Scan intake and quality | 20 | 20.5 | 35.0 | 62.0 | 37.0 |
| EP-08 | Anatomy and measurement | 19 | 24.0 | 40.0 | 70.0 | 42.3 |
| EP-09 | Design workspace and regeneration | 15 | 27.0 | 44.0 | 75.0 | 46.3 |
| EP-10 | Review, approval and export | 15 | 22.0 | 36.5 | 62.0 | 38.3 |
| EP-11 | UI shell, 3D viewer and reporting | 21 | 28.5 | 47.5 | 81.0 | 49.9 |
| EP-12 | Quality engineering, security, operations (incl. stabilisation) | 36 | 47.2 | 86.7 | 159.2 | 92.2 |
| EP-13 | Technology experiments and benchmarks | 14 | 20.0 | 34.5 | 54.5 | 35.4 |
| EP-14 | Pilot readiness and external verification | 12 | 19.0 | 31.0 | 53.0 | 32.7 |
| EP-15 | Next version and deferred (not scheduled) | 14 outline | — | — | — | — |
| **Total** | | **338** | **443.2** | **757.7** | **1,317.2** | **798.2** |

## 6. Implementation Decision Record (IDR) — decisions taken under delegation

Status of every IDR: **ratified 2026-11-17** by the engineering lead and product owner (DECISION_RECORD_2026-11-17.md): 33 Approved, 4 Approved-provisional (IDR-03, IDR-20, IDR-25, IDR-29), 1 Approved-conditional (IDR-33, lock-in at M1 exit). "Provisional" marks a default the clinic technician may later change through a versioned op or configuration change (no code change to the approval chain). Reversibility: R = cheap to revise, M = revision needs an op_version bump or migration, H = revision after M2 needs re-planning.

| ID | Closes | Decision | Rejected alternatives | Rationale | Affects | Rev. |
|---|---|---|---|---|---|---|
| IDR-01 | OQ-FS-01, TD-07, GAP-A03/C06 | Positive closure is a **pinned terminal operation**: recorded in the op list, always evaluated last, position not editable; new design starts with 0 ops; BL-017 wording corrected | (a) first op; (c) free position | Keeps every design op topology-preserving (anchors stay valid) and the base exactly on the configured plane; zero displacement above the base | FN-KOP-06, FN-KRP-01, FN-DES-01/02 | M |
| IDR-02 | OQ-FS-02, GAP-A05 | Measurement formula = **enumerated formula type** {CI, CVA, CVAI_min_denominator, CVAI_max_denominator, HC} + parameters; DATA-02 "formula expression" stores the type code and a human-readable string | Free expression language with evaluator | Testable against VER-01 phantoms; no evaluator attack surface | FN-CFG-05, FN-MEA-01, DS-10 | M |
| IDR-03 | OQ-FS-03, TQ-18, GAP-M11/M12 | Definitions gain three fields: `contour_selection_rule` {enclosing_origin_projection, largest_perimeter, technician_pick}, `diagonal_centre_rule` {origin_projection, contour_area_centroid}, `angle_reference_axis` {AP, ML}; kernel supports all options; the two shipped presets (30°, 40°, DEC-027) carry enclosing_origin_projection / origin_projection / AP (provisional, technician-editable per definition); non-convex diagonals use the **outermost** intersections | Single hard-coded rule | Technician owns definitions (DEC-027); no kernel change needed when the clinic chooses differently | FN-KMS-02/04, FN-CFG-05/06, FN-MEA-01 | R |
| IDR-04 | OQ-FS-04, GAP-M16 | Approval binds **one measurement set explicitly selected** by the technician from the current (non-superseded) sets on the design's frame; no pre-selection | Latest set auto-bound; all sets | A pre-selection acts as a default (SAF-02) | FN-REV-04, DS-20 | R |
| IDR-05 | OQ-FS-06, GAP-C02, TD-22 | Error catalogue = **RTM v0.3 codes** (PRESCRIPTION_MISSING, ZONE_OVERLAP_NOT_ALLOWED; CN-11 names retired); catalogue `error/1` frozen at M0 exit; `/api/v1` | Keep both name sets | One contract for UI and tests | FN-API-02, XC-FND-06 | R |
| IDR-06 | OQ-FS-07, GAP-C04 | Audit hash covers only the **non-erasable core** (seq, type, user/role, object refs, time, prev_hash); summaries live in an erasable table outside the hash. Blob erasure via a **separate privileged purge credential** held by the engineering lead, usable only by the FN-CAS-08 procedure, every use audited | Blank summaries inside hashed rows (breaks chain); no erasure | Satisfies SEC-11 without breaking tamper evidence | FN-AUD-01, FN-BLB-04, FN-CAS-08, DS-18 | H |
| IDR-07 | OQ-FS-08, TQ-02, TQ-03, TQ-20, TD-13 | **Deployment:** Docker Compose on one Linux x86-64 host in the same region as the Supabase project (provider chosen in M1 by: region match, Docker, rlimits/seccomp, backups); C0 = Caddy reverse proxy (TLS ≥ 1.2, same-origin `/api`), Next.js, FastAPI, worker pool. **Data:** direct Postgres connections with roles app_rw / worker_rw / audit_append (INSERT-only) / admin_ro; Storage only through IF-04 with service credentials. **Backup:** platform DB backup + **separate daily encrypted Storage backup with restic** to a different provider/account. **Sandbox:** parse in a child process with rlimits, read-only FS, no network, non-root, Docker default seccomp. **Fallback if X-07 shows the app credential can overwrite/delete:** IF-04 enforces no-overwrite (exists-check, content addressing) and the bucket policy denies delete; if a policy cannot deny delete, blobs move to S3-compatible storage with object lock | Kubernetes; PostgREST/RLS-centred design; filesystem CAS | Smallest operable footprint for one clinic (≤ 5 users, A-16); keeps ADR-005/007/012 semantics | XC-FND-07/08/09, FN-BLB-*, FN-OPS-05 | M |
| IDR-08 | TQ-04, TD-14 | **Own session auth** (argon2id, server-side sessions, SD-01 lockout, SD-02 idle timeout, CSRF token); Supabase Auth not used | Supabase Auth JWT | One place for authn/authz/audit; no browser-held tokens | FN-IAM-* | M |
| IDR-09 | TQ-09, X-08 | **Python 3.12**, linux/amd64 only for MVP images; Node.js active LTS at M0, pinned; package managers **uv** (Python) and **pnpm** (JS); versions of LIBRARY_COMPARISON_v1.0 pinned in lockfiles and re-checked by X-08 | 3.13; arm64 images | numpy 2.5/scipy 1.18 need ≥ 3.12; widest wheel availability; one architecture keeps bit-exact determinism testable | All | R |
| IDR-10 | TQ-05, TQ-11, TD-02, TD-03, TD-05 | **Lean kernel:** numpy/scipy + own algorithms; **one own deterministic BVH (numba, fastmath off, parallel off)** shared by self-intersection, closest point, ray casting and signed distance; own port of Shewchuk predicates; libigl/trimesh/CGAL/PyMeshLab are CI oracles only. Fallbacks: numba fails X-06 → C++ extension (nanobind) for the same inner loops; own BVH fails X-01 performance → libigl (MPL-2.0) for closest point | Open3D in production (Embree threading, tie handling uncontrolled); trimesh in production | Full control of tie rules and determinism (VER-07); minimal SOUP; one spatial index to test | XC-SHR-01/02, FN-KVL-05, FN-KAN-01, FN-KCP-01 | H |
| IDR-11 | TQ-06 | Windowed-sinc smoothing **implemented in-house** (VTK not shipped) | VTK filter | Avoids a large SOUP item for one Should feature | FN-KOP-12 | R |
| IDR-12 | TQ-07, TD-11, OQ-FS-17 (part) | Display LOD: **fast-simplification** (MIT) if deterministic in X-01, else meshoptimizer; recorded op cleanup.decimate (Should): own constrained QEM | VTK QEM | LOD is display-only (INV-10); recorded op needs manifoldness and determinism | FN-KOP-03/04 | R |
| IDR-13 | TQ-08, TD-12 | Cap triangulation: **own exact ear clipping** (orient2d); mapbox-earcut as test oracle | earcut in production | Exactness on near-collinear contours | FN-KOP-06 | R |
| IDR-14 | TQ-10, OQ-FS-24, TD-18 | Deviation image for the PDF by **own orthographic z-buffer rasteriser**; PDF by WeasyPrint | VTK off-screen; headless browser | No GPU/browser in worker; deterministic images | FN-RPT-02 | R |
| IDR-15 | TQ-25 | Blob container **jude-arr/1** (own minimal header, little-endian raw arrays, no pickle, no zip timestamps) | .npy/.npz | Canonical bytes for content addressing | XC-FND-12, DS-01 | M |
| IDR-16 | TQ-21, TQ-23 | trimesh 5.x oracle-only; matplotlib only in analytics notebooks, never shipped | trimesh utilities in production | SOUP and licence control | FN-OPS-07, FN-OPS-09 | R |
| IDR-17 | TQ-17 | OBJ polygons k > 3: fan triangulation if convex in the Newell plane, exact ear clipping otherwise | Fan always | Correct for concave polygons | FN-KIO-03 | R |
| IDR-18 | TQ-26, TQ-19 | Guard: normal-flip threshold 0 with exact orient3d fallback near 0; transition width T ≥ 0 allowed (T = 0 accepted only if the guard passes); clinic ranges via magnitude_ranges (SAF-07) | Tolerance-based flip test | No arbitrary epsilon; technician keeps control | FN-KOP-10/13 | R |
| IDR-19 | TQ-15, TQ-16 | Kernel container images retained for the case retention period; no cross-host determinism fallback is pre-approved — decided only on BM-03 evidence | Shorter retention; pre-approved tolerance | Approved designs must be reproducible (ADR-010) | FN-KRP-01, FN-OPS-04 | R |
| IDR-20 | OQ-FS-09, -10, -11, -19, -20 | **Revised by CN-2026-11-17:** the zone profile is an op parameter (FN-KOP-15: plateau, peak or custom monotone curve) and zones may be free-form contours (FN-KOP-14); plateau + smoothstep remains the default preset. Other provisional geometric defaults (technician may change by op_version): ellipse orientation from the projected vertical axis (fallback A-P axis); angle-weighted vertex normals; smoothing blend smoothstep; global length = whole-surface extent along the axis; circumference = contour perimeter at the chosen level | Continuous fall-off; area-weighted normals | Matches FR-050 AC, 05 §3.6, 07 §6.3; A-15/A-22 confirmed as provisional (DR item 18) | FN-KOP-05/08/09/10/12 | M |
| IDR-21 | OQ-FS-12 | Closure (wall/cap) and boundary-masked vertices excluded from deviation statistics and drawn neutral grey | Distance to base plane | No scan counterpart exists | FN-KCP-01 | R |
| IDR-22 | OQ-FS-13 | Degenerate faces = **exact** collinearity (orient predicates) or repeated index, i.e. ε_area = 0 under exact arithmetic; slivers reported as a diagnostic (min angle) only | Fixed ε_area constant | No arbitrary tolerance; scale-independent | FN-KVL-02 | R |
| IDR-23 | OQ-FS-14, GAP-M02 | Landmark snap-distance limit = engineering constant 2 × max LOD deviation reported by FN-KOP-04 (not a clinical key) | Clinic key | It guards a display artefact, not a clinical decision | FN-ANA-02, FN-KAN-01 | R |
| IDR-24 | OQ-FS-15, -21, -22 | No unit proposal (all four bounding boxes shown); "newer scan" = upload time (acquisition date shown as information); plausible size compares sorted extents at import | Heuristic proposal | Avoids anchoring the technician; upload time always exists | FN-SCN-04/08, FN-REV-04, FN-EXP-01 | R |
| IDR-25 | OQ-FS-16, -17, -28, TQ-12 | Hole filling only on technician-selected loops ≤ P; Liepa triangulation + refinement, fairing behind a flag; n_max set from BM-02 statistics (until then hole filling runs only in test configurations); cleanup.decimate kept as a recorded Should op enabled only when a scan exceeds N | Fill all loops; fairing always | Matches RG-04 and BL-028; bounds O(n³) cost | FN-KOP-02/03, FN-SCN-11 | R |
| IDR-26 | OQ-FS-18 | Sector coverage = ray-hit fraction ≥ c_min; c_min is clinic configuration | Area criterion | Deterministic, matches ALG-34 | FN-KAN-03 | R |
| IDR-27 | OQ-FS-23 | Manifest format jude-manifest/0.1 JSON + published JSON Schema | Other | Already specified in 07 §6.7 | FN-KEX-01/02 | R |
| IDR-28 | OQ-FS-25, OQ-FS-27 | Add two requirements in RTM v0.4: case list/search; warning for measurements over synthetic surface | Keep as navigation / backlog AC | Traceability of a navigation need and of a safety-relevant warning | FN-CAS-02, FN-KMS-06 | R |
| IDR-29 | OQ-FS-26, GAP-M18 | Prescription: technician attaches; technician and clinic admin may view/download (every access logged, SEC-15/16); accepted types per FR-164; **maximum file size 20 MB** (provisional product limit for scanned multi-page PDFs) | Admin attaches; no limit | Matches FR-164 actor; bounds storage abuse | FN-CAS-06/07 | R |
| IDR-30 | OQ-FS-37, GAP-M08 | Scan winding: recorded op `normalise_orientation` proposed to the technician when inconsistency or an inward hint is found (no silent repair); closure faces oriented automatically by construction | Automatic repair; never | No silent repair (05 §6.2); zones/offsets need outward normals | FN-KVL-04, FN-KOP-05/06 | R |
| IDR-31 | OQ-FS-38, GAP-C10 | M1 **walking skeleton** on a synthetic phantom with a test-only frame fixture (flag test_only, cannot reach production — FN-CFG-07); product milestones follow the dependency order (anatomy before design) | Re-sequence only | Early end-to-end risk reduction without violating FR-032 | XC-WSK-01 | R |
| IDR-32 | OQ-FS-05, -33, -35, -36 | RTM v0.3 governs configuration approval (backlog BL-030/BL-115 texts corrected); denoising, reconstruction, remeshing, shell, wall thickness and 3MF stay out of MVP; BL-112 retired; DATA-18 cohort descriptors not built in MVP | Add scope | Scope discipline; no approved requirement | MVP_SCOPE §6–7 | R |
| IDR-33 | TQ-01, OQ-FS-30 | FS v1.0 and TD v1.0 set approved **for implementation** (not Baselined); library lock-in (TD-02/03/05/11, ADR-002) signed at M1 exit on X-01/X-02/X-06/X-08 evidence (XC-EXP-LOCK) | Wait for full baseline | Planning and M0 work need a fixed basis; library choice needs evidence | All | M |
| IDR-34 | — (tooling) | Monorepo on GitHub; GitHub Actions; trunk-based development with short-lived branches; Conventional Commits with task-ID trailer; CODEOWNERS; Dependabot; SQLAlchemy 2 + Alembic + psycopg 3; Caddy; restic | GitLab; GitFlow; Renovate | Lowest operating overhead for a small team; Dependabot avoids an extra hosted tool | DEVELOPMENT_STANDARDS, REPOSITORY_STRUCTURE | R |
| IDR-35 | Scope | 7 Should functions promoted to Core; 19 Should functions ordered by cut line; 8 Next, 5 Deferred | Build all Should items as Core | Protects the end-to-end workflow and safety controls first | MVP_SCOPE | R |
| IDR-36 | Planning | 2-week sprints; focus factor 0.7; estimates in ideal pd with three points; re-estimate at every milestone exit; commitments at P80 | Story points | Estimates convertible to cost and staffing; uncertainty explicit | DEVELOPMENT_ROADMAP | R |
| IDR-37 | CN-2026-11-17 | Adopt change notice CN-2026-11-17: CH-01…CH-05 into MVP-Core, CH-06…CH-12 into MVP-Should (CH-12 decided by IDR-38), CH-13 to v1.1; milestone M4 split into M4a/M4b; XC-PLT-13 observation of a helmet session in M0 gates all new functions | Keep v1.0 scope | Technicians' current CAD (Rodin4D) shows these tools in daily use; parity on zones and live feedback is needed for VER-10 (design time) to be met | MVP_SCOPE v1.1, WBS v1.1 | R |
| IDR-38 | OD-09, DEC-028 (amended), CH-12 | Whole-surface smoothing (Rodin4D "Complete Smoothing") allowed as an explicit, recorded, replayable op: smooth.windowed_sinc with region = whole scan-origin surface; local smoothing stays primary; no default parameters (technician enters iterations/pass-band); closure faces excluded; max/RMS deviation shown before save; measurements refuse smoothed artifacts (FR-179) | (a) local only (DEC-028 as was) — forces technicians to smooth in Artec Studio, outside the audit trail; (c) automatic smoothing on import — silent change of the measured surface | Technicians used it in the observed design history; doing it inside Jude keeps it visible, reversible and traceable; deviation report bounds the effect | TSK-KOP-12-KG (MVP-Should, cut-line rank 5) | R |

Decisions **not** taken (outside a software team's authority or needing data) are listed as open decisions in §9.2 and external dependencies in §9.3.

## 7. Development sequence

### 7.1 Ordering rules

1. **Contracts before implementations.** Kernel contracts (XC-FND-12), DB schemas (XC-FND-05), API contract pipeline (XC-FND-06) and the error catalogue (IDR-05) come first; every later task depends on them.
2. **Robust primitives before geometry.** Exact predicates (XC-SHR-01) and the shared BVH (XC-SHR-02) precede self-intersection, closest point, closure and measurement.
3. **Function dependencies of FUNCTION_CATALOG are honoured** as finish-to-start edges between the primary tasks; seven soft edges toward Should functions were removed (MVP_SCOPE §5).
4. **Implementation → verification → UI.** TT-V depends on TT-K; TT-U depends on the function's TT-B/TT-J and on the UI tasks of upstream functions; all UI after M1 depends on the shell (FN-UIX-01).
5. **Gates are tasks.** Decision ratification (XC-FND-01), library lock-in (XC-EXP-LOCK), VER-22 (XC-PLT-01), RC1 feature freeze (XC-REL-01) are explicit nodes in the dependency graph.
6. **Milestone consistency.** No task depends on a task of a later milestone (automatic check: 0 violations).
7. **Pilot work after RC1.** Pilot deployment, clinic configuration, physical verification, usability and agreement studies, final E2E and security suites depend on XC-REL-01.

### 7.2 Milestones (content and exit criteria in DEVELOPMENT_ROADMAP §2)

| Milestone | Goal | Tasks | ML pd |
|---|---|---|---|
| M0 Foundations & decisions | Repo, CI, standards, schema, platform services, kernel contracts, predicates, decision record, observation of a helmet session (XC-PLT-13) | 46 | 84.5 |
| M1 Kernel core & walking skeleton | STL in → validity → closure → replay → STL out on phantoms; BVH; library lock-in | 56 | 147.9 |
| M2 Intake, configuration, governance | Cases, consent, prescription, configuration, scan intake + gate + cleanup, privacy controls, backup, VER-22 | 90 | 180.7 |
| M3 Anatomy & measurement | Landmarks, frame (+ manual fine-tuning), CI/CVA/CVAI/HC, definitions, tape measure; real-scan experiments | 43 | 88.0 |
| M4a Design workspace — operations | Zones (free-form contour, profile editor, symmetric), adjustments (incl. two-level elongation), offset, smoothing, op list, regeneration | 40 | 113.5 |
| M4b Design workspace — live feedback | Live design metrics, original/modified overlay, signed-distance field moved from M5, 2D sections, view cube, templates | 20 | 42.4 |
| M5 Review, approval, export | Review job, validity, approval binding, export + re-import | 20 | 41.8 |
| M6 Hardening & system verification | RC1, reports, E2E, security suite, benchmarks, NFR values | 14 | 35.9 |
| M7 Pilot readiness | Clinic configuration, physical verification, usability/agreement, pilot deployment, go/no-go | 9 | 23.0 |

### 7.3 Critical path

Unconstrained (infinite staff) critical path = **116 WD**: XC-FND-01 → XC-FND-02 → XC-FND-12 → XC-EXP-06 → XC-SHR-02 (BVH) → TSK-KVL-05-K (self-intersection) → TSK-KOP-13-K (guard) → TSK-KOP-10-K (zones) → TSK-KOP-14-K/U (free-form contour + editor) → TSK-KOP-16-U (symmetric zones) → XC-STB-M4a-FRONTEND → XC-REL-01 → TSK-OPS-12-C → XC-PLT-05 → XC-PLT-04 → XC-PLT-08 → XC-PLT-11. With real staffing the schedule is 2.8–5 × longer than this path, i.e. **resource-bound**: adding the right roles shortens it; reordering does not.

## 8. Effort estimate

### 8.1 Totals (ideal person-days)

| Scope | Optimistic | Most likely | Pessimistic | PERT |
|---|---|---|---|---|
| MVP-Core | 392.2 | 665.2 | 1,153.2 | 700.8 |
| MVP-Should | 51.0 | 92.5 | 164.0 | 97.5 |
| **MVP total** | **443.2** | **757.7** | **1,317.2** | **798.2** |
| Of which CN-2026-11-17 | — | 79.9 | — | — |
| Next (v1.1) outline, not in totals | 72 | 135 | 225 | — |

Monte Carlo (200 runs, task-level triangular + correlated bias Tri(0.9, 1.0, 1.4)): **P10 821 · P50 915 · P80 1,009 · P90 1,070 pd**. Planning value for budgeting: **P80 ≈ 1,010 pd**; uncertainty range **820–1,070 pd** (P10–P90); hard bounds 443–1,317 pd.

### 8.2 By role pool (ML / PERT)

| Pool | ML | PERT | Share |
|---|---|---|---|
| Kernel engineering | 216.1 | 226.3 | 29 % |
| Backend engineering | 203.7 | 215.1 | 27 % |
| Frontend engineering | 161.6 | 170.4 | 21 % |
| QA / DevOps (incl. geometric verification) | 146.8 | 155.4 | 19 % |
| External roles (EL, PO, PS, clinic) | 29.5 | 31.0 | 4 % |

### 8.3 By milestone and pool (ML pd)

| Milestone | Tasks | Opt | ML | Pess | PERT | Kernel | Backend | Frontend | QA/Ops | External |
|---|---|---|---|---|---|---|---|---|---|---|
| M0 | 46 | 50.5 | 84.5 | 143.0 | 88.5 | 24.0 | 33.5 | 4.0 | 17.0 | 6.0 |
| M1 | 56 | 87.8 | 147.9 | 255.2 | 155.7 | 72.6 | 14.3 | 12.1 | 47.9 | 1.0 |
| M2 | 90 | 102.7 | 180.7 | 323.4 | 191.3 | 34.9 | 65.9 | 53.4 | 22.5 | 4.0 |
| M3 | 43 | 51.8 | 88.0 | 155.9 | 93.3 | 25.7 | 28.7 | 25.0 | 8.6 | 0 |
| M4a | 40 | 64.3 | 113.5 | 194.0 | 118.7 | 50.3 | 15.4 | 26.4 | 21.4 | 0 |
| M4b | 20 | 25.2 | 42.4 | 73.3 | 44.7 | 6.6 | 13.3 | 20.0 | 2.5 | 0 |
| M5 | 20 | 25.2 | 41.8 | 72.7 | 44.2 | 2.0 | 24.6 | 14.2 | 1.0 | 0 |
| M6 | 14 | 21.5 | 35.9 | 59.8 | 37.5 | 0 | 7.0 | 3.5 | 20.9 | 4.5 |
| M7 | 9 | 14.2 | 23.0 | 39.9 | 24.4 | 0 | 1.0 | 3.0 | 5.0 | 14.0 |

### 8.4 By task type (ML pd)

| Type | Tasks | ML | Type | Tasks | ML |
|---|---|---|---|---|---|
| TT-K kernel (+1 whole-surface smoothing KG) | 56 | 159.0 | Foundation (XFND) | 12 | 41.0 |
| TT-U UI | 60 | 144.0 | Experiments (XEXP) | 14 | 34.5 |
| TT-B domain/API | 56 | 104.0 | Pilot readiness (XPLT) | 12 | 31.0 |
| TT-V verification | 55 | 74.5 | CI tooling (TT-C) | 9 | 29.0 |
| Stabilisation + RC1 (XSTB) | 24 | 50.7 | Synchronous services (TT-A) | 13 | 19.0 |
| TT-J jobs | 16 | 34.5 | Kernel shared (XSHR) | 4 | 18.5 |
| TT-O procedures | 7 | 18.0 | | | |

**Why more than backlog v0.3 (308 ideal days):** the backlog sized 107 user stories at S=2/M=4/L=8 days; this plan sizes 310 tasks bottom-up and adds what the stories left implicit — independent geometric verification (65.5), own robust primitives chosen in TD v1.0 (exact predicates + BVH, 18.5), separate UI tasks (115), experiments X-01…X-08 and benchmarks (34.5), stabilisation reserve and RC1 (45.8) and pilot evidence work (29). *(Figures in this paragraph are the v1.0 basis; CN-2026-11-17 adds 79.9 pd, mostly kernel zones and workspace UI.)*

### 8.5 Duration scenarios (working days; sprint = 10 WD)

| Scenario | Composition | Plan (ML) | P50 | P80 | Sprints at P50 / P80 |
|---|---|---|---|---|---|
| S1 Lean 2.5 FTE | 1 kernel, 1 full-stack, 0.5 QA/DevOps (+ external 2 × 0.5) | 607 | 723 | 802 | 73 / 81 |
| S2 Reference 4 FTE | 1 kernel, 1 backend, 1 frontend, 1 QA/DevOps (+ external) | 413 | 492 | 546 | 50 / 55 |
| S3 Balanced 6 FTE | 2 kernel, 2 backend, 1 frontend, 1 QA/DevOps (+ external) | 324 | 385 | 431 | 39 / 44 |

To convert to dates: start date + WD ÷ (working days per week) with holidays and leave of the actual team; re-run the generator with real FTE values. **Recommendation:** staff towards S3 for the geometry and backend pools in M0–M2 (the kernel is the long pole until the walking skeleton; backend is the long pole in M2 and M5).

## 9. Registers

### 9.1 Technical dependency register

| ID | Dependency | Version policy (checked 2026-11-15) | Licence | Used by | Status / decided by | Fallback |
|---|---|---|---|---|---|---|
| TD-R01 | CPython | 3.12.x pinned in image | PSF-2.0 | All Python | IDR-09 | 3.13 after X-08 |
| TD-R02 | numpy / scipy | 2.5.4 / 1.18.1 pinned | BSD-3 (+0BSD, CC0 parts) | Kernel | R-MVP | — |
| TD-R03 | numba | 0.68.1 pinned; fastmath off, parallel off | BSD-2 | BVH, predicates, triangle tests | Candidate → X-06 | C++/nanobind extension |
| TD-R04 | Shewchuk predicates (own port) | in-repo | Public domain | XC-SHR-01 | R-MVP | Python fractions (slow path) |
| TD-R05 | fast-simplification / meshoptimizer | 0.2.0 / 0.2.30a0 | MIT | Display LOD | Candidate → X-01 | Own QEM |
| TD-R06 | libigl, Open3D | 2.6.3 / 0.20.0 | MPL-2.0 core / MIT | Oracle; fallback closest point | Candidate (IDR-10) | Own BVH |
| TD-R07 | trimesh, numpy-stl, mapbox-earcut | 5.2.1 / 4.1.4 / 2.1.0 | MIT / BSD-3 / ISC | Oracles, second STL reader | Oracle | — |
| TD-R08 | CGAL, PyMeshLab | 6.1.x / 2025.7 | GPL | CI oracle container only | Oracle, never shipped | — |
| TD-R09 | jsonschema, rfc8785 | 4.26.0 / 0.1.4 | MIT / Apache-2.0 | Op registry, manifest, JCS | R-MVP / candidate (RFC vectors) | Own JCS |
| TD-R10 | FastAPI + pydantic | 0.163.1 / 2.14.3 | MIT | API | R-MVP | — |
| TD-R11 | SQLAlchemy, Alembic, psycopg | 2.1.8 / 1.20.1 / 3.3.9 | MIT / MIT / LGPL-3.0 (dynamic) | Data layer | R-MVP | — |
| TD-R12 | Supabase Postgres + Storage | Platform | Service terms | Data layer | SD-05; X-07 | S3 storage with object lock |
| TD-R13 | WeasyPrint | 70.0 | BSD-3 | Report PDF | R-MVP (Should) | — |
| TD-R14 | Next.js, React, TypeScript | next 16.4.6, react 19.3.1 | MIT | UI | R-MVP | — |
| TD-R15 | three.js, three-mesh-bvh | 0.187.0 / 0.9.18 | MIT | Viewer | R-MVP | vtk.js |
| TD-R16 | pytest, hypothesis, Playwright, vitest | 9.2.0 / 6.170.15 / 1.65.1 / 5.1.0 | MIT / MPL-2.0 / Apache-2.0 / MIT | Tests (not shipped) | DEV | — |
| TD-R17 | Caddy, restic | pinned at M1 | Apache-2.0 / BSD-2 | Proxy, Storage backup | IDR-07 (add to allow-list check, FN-OPS-02) | nginx / rclone + age |
| TD-R18 | uv, pnpm, GitHub Actions, Dependabot | pinned at M0 | MIT/Apache, MIT, service | Tooling | IDR-34 | — |

Rules: exact pins in lockfiles; any upgrade of a kernel-path dependency triggers the full determinism and golden-hash regression (R-29, FN-OPS-04) and an op_version/kernel_version review.

### 9.2 Open decisions that remain (not decidable by the software team)

| ID | Decision | Owner | Needed by | Blocks (tasks) |
|---|---|---|---|---|
| OD-01 | Clinic configuration values: landmark set, frame rule, gate thresholds, coverage sectors, c_min, base convention, export frame, checklist, magnitude ranges (DEC-029, DEC-027) | Clinic technician | M7 (XC-PLT-04) | Pilot only — software built with NOT_SET + test configs |
| OD-02 | Pilot success thresholds for design time and measurement agreement (DEC-030) | Clinic | M7 | XC-PLT-08 interpretation |
| OD-03 | Pilot-entry values N, S, face cap, LOD budget, n_max, time budgets (NFR-01…04, OQ-FS-29) | Engineering lead + clinic IT, from BM-02/BM-04/BM-05 | M6 (XC-PLT-03) | Pilot; performance pass/fail |
| OD-04 | Team composition and start date (S1/S2/S3 or other) | Product owner / CEO | Before M0 sprint 1 | Calendar dates only |
| OD-05 | Hosting provider for the container host (criteria fixed in IDR-07) | Engineering lead | M1 (XC-FND-07) | Staging |
| OD-06 | Accept cross-host determinism fallback if BM-03 fails (IDR-19) | Engineering lead + QA lead | M6 | Only if BM-03 fails |
| OD-07 | Regulatory/legal questions RQ-01…15, LQ-03 data residency (deferred by owner) | Experts when the owner decides | Before any claim beyond the pilot | None in MVP build |
| OD-08 | Baselining of RTM (MA-01 spot-check, independent re-audit) | Named reviewer | Before v1.0.0 release | Formal baseline only |
| OD-09 | **Closed 2026-11-17 by IDR-38** — whole-surface smoothing allowed as an explicit recorded op | — | — | — |

### 9.3 External dependencies

| ID | Dependency | Provider | Gate task | Earliest need | Consequence if late |
|---|---|---|---|---|---|
| EXT-01 | VER-22 privacy inspection record | Privacy specialist | XC-PLT-01 | End of M2 | No real scans → BM-02, X-02R, X-03, X-05, pilot slip |
| EXT-02 | Clinic IT inventory (browsers, PCs, network) | Clinic IT | XC-PLT-02 | M2 | Viewer budget and E2E browser matrix unknown |
| EXT-03 | Benchmark evidence for NFR values | Engineering (needs EXT-01, EXT-02) | XC-PLT-03 | M6 | Pilot entry blocked |
| EXT-04 | Clinic technician time: configuration entry, usability sessions, manual measurements | Saigak Orto | XC-PLT-04, XC-PLT-08 | M7 | Pilot evaluation blocked |
| EXT-05 | ≥ 3 real Artec exports per format | Saigak Orto (after EXT-01) | XC-EXP-02R, XC-PLT-06 | M3 | INT-08 unverified |
| EXT-06 | Rodin4D Neo access and production of a physical positive | Saigak Orto production | XC-PLT-07 | M7 | VER-06/VER-16 open |
| EXT-07 | Legal review of licence allow-list / SOUP | External reviewer | XC-PLT-10 | M6 | Release blocked (licence risk) |

The development risk register is DEVELOPMENT_RISK_REGISTER_v1.1.csv.

## 10. Governance

| Topic | Rule |
|---|---|
| Decision process | New technical choices → ADR in `docs/adr/` (status Proposed → Accepted by engineering lead); product/scope choices → decision record in the project; IDs never reused |
| Change control | Change to an approved requirement → RTM row change + impact on WBS tasks (generator re-run) + test catalogue update in the same PR |
| Milestone exit review | Exit criteria of DEVELOPMENT_ROADMAP §2 checked by EL + QA; re-estimate remaining work; update risk register; record in `docs/milestones/Mx-exit.md` |
| Progress reporting | Per sprint: tasks done vs planned (pd), burn-up against P50/P80, CI health, open P1 defects, gate status (EXT-01…07) |
| Re-planning triggers | Any milestone > P80; an experiment failing its pass criterion; a gate late by > 1 sprint; scope change |
| Pilot entry criteria | RC1 complete; all CI gates green; VER-22 recorded; clinic configuration published (non test_only); NFR values set; VER-02/06/16 recorded; legal licence review done; go/no-go record (XC-PLT-11) |

## 11. Readiness for transfer to Claude Code

### 11.1 Assessment

| Criterion | Evidence | Status |
|---|---|---|
| Requirements and functions traceable to tasks | 185/185 MVP requirements (11 proposed), 157/157 MVP functions, 67/67 subfunctions mapped; acceptance criteria from FS v1.0 and CN-2026-11-17 | Green (RTM v0.4 rows pending) |
| Technical design to implementation level | TD v1.0 set: 61 algorithms, 25 data structures, 12 interfaces, 226 function specifications | Green |
| Blocking questions | All 7 functional + B1/B2 technical questions closed by IDR (delegated) | Green — XC-FND-01 ratified 2026-11-17 |
| Task definitions | 338 tasks with function, requirement, deliverable, completion criteria, tests, DoD, dependencies, effort | Green |
| Repository structure, standards, test plan | REPOSITORY_STRUCTURE_v1.0, DEVELOPMENT_STANDARDS_v1.0 (unchanged), DEVELOPMENT_TEST_PLAN_v1.1 | Green |
| Library choices | Proposals + experiments; lock-in at M1 exit | Amber (by design) |
| Environment access | No repository, Supabase project credentials or container host exist yet | Amber — created in M0/M1 tasks |
| Real data | Gated by VER-22 | Red for real data, not needed before M2 end |
| Team | Not fixed (OD-04) | Amber — affects dates, not readiness |

**Verdict: READY to start implementation in Claude Code for M0 and M1 (synthetic data only), with two conditions:** (1) decision record XC-FND-01 — done 2026-11-17; (2) create the GitHub repository and give Claude Code access; (3) no real patient data in any Claude Code session — real scans only on the pilot/staging stack after VER-22. Readiness score: 7 of 9 criteria green or amber-by-design; overall ≈ **85 %** for M0–M1, ≈ 60 % for M2 onwards until X-07 and VER-22 are done.

### 11.2 Hand-over package for the first Claude Code session

1. `CLAUDE.md` at the repository root containing: intended-use boundary (no diagnosis/prescription wording, FR-045/NFR-06); kernel purity and determinism rules (DEVELOPMENT_STANDARDS §5); "no defaults for clinical/production values" rule (SAF-02); ID conventions (task, function, requirement, test); commands (`uv run pytest`, `pnpm test`, `docker compose up`); definition of done; "never commit secrets or patient data".
2. This plan, MVP_SCOPE, the WBS and dependency CSVs, REPOSITORY_STRUCTURE, DEVELOPMENT_STANDARDS, DEVELOPMENT_TEST_PLAN under `docs/plan/`, and the TD v1.0 set under `docs/design/`.
3. First sprint queue (S2 reference order): XC-FND-01 (done 2026-11-17), XC-FND-02, XC-FND-04, XC-FND-05, XC-FND-12, XC-FND-10 (human), XC-EXP-08, XC-FND-03, XC-FND-11, XC-SHR-01.
4. Working rule for Claude Code: one task ID per branch/PR; PR description lists function, requirement and test IDs; every PR passes the CI stages before merge; geometric verification (TT-V) PRs are reviewed by a human who did not write the kernel task.

## 12. Deliverables of this stage

| # | File | Content |
|---|---|---|
| 0 | CHANGE_NOTICE_CN-2026-11-17.md | Rodin4D observation → changes CH-01…CH-16 and impact |
| 1 | IMPLEMENTATION_PLAN_v1.1.md | This document |
| 2 | MVP_SCOPE_v1.1.md | MVP-Core / Should / Next / Deferred with criteria, cut line, technical dependencies |
| 3 | WORK_BREAKDOWN_STRUCTURE_v1.1.csv | 32 columns; Epic → Module → Feature → Task → Subtask; effort, skills, tests, DoD, status, critical path |
| 4 | DEVELOPMENT_ROADMAP_v1.1.md | Milestones, entry/exit criteria, scenarios, reference sprint plan, gates |
| 5 | TASK_DEPENDENCY_MATRIX_v1.1.csv | 1,391 finish-to-start edges with kind (FUNC, SAME, ENAB, DEC, DATA, EXPR, STAB, REL) and critical-path flag |
| 6 | REPOSITORY_STRUCTURE_v1.0.md | Monorepo layout, layer → directory mapping, import rules, CI/CD, environments |
| 7 | DEVELOPMENT_STANDARDS_v1.0.md | Coding, naming, branching, commits, review, dependencies, logging, errors, documentation, DoD |
| 8 | DEVELOPMENT_TEST_PLAN_v1.1.md | Test levels, task → test mapping, fixtures, oracles, CI gates, milestone entry/exit |
| 9 | DEVELOPMENT_RISK_REGISTER_v1.1.csv | Development risks with probability, impact, triggers, mitigations, owners, linked tasks |

The WBS and dependency CSVs are produced by a deterministic generator from the catalogue, mapping, FS and RTM (seed 20261115), so they can be regenerated after any scope or estimate change.
