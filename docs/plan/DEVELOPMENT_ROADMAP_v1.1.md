# Development Roadmap v1.1 — Jude cranial remolding helmet design software

| Field | Value |
|---|---|
| Document | DEVELOPMENT_ROADMAP_v1.1.md |
| Version / date | v1.1 · 2026-11-17 — CN-2026-11-17 applied (M4 split into M4a/M4b; 11 CAD functions added); supersedes v1.0 |
| Status | Draft for ratification with IMPLEMENTATION_PLAN_v1.1 (decisions IDR-01…37) |
| Inputs | WORK_BREAKDOWN_STRUCTURE_v1.1.csv, TASK_DEPENDENCY_MATRIX_v1.1.csv, MVP_SCOPE_v1.1.md, CHANGE_NOTICE_CN-2026-11-17.md |
| Calendar rule | **No dates.** Durations are working days (WD) from the start of M0 and 2-week sprints (S01, S02, …). Effort first (IMPLEMENTATION_PLAN §8), then durations per staffing scenario. Dates are derived only after team size and start date are fixed (§7). |

## 1. Summary

- **Nine milestones** M0, M1, M2, M3, M4a, M4b, M5, M6, M7 in dependency order: foundations → kernel core + walking skeleton → intake/configuration/governance → anatomy/measurement → design operations (zones, profiles, symmetric zones) → live design feedback (metrics, overlay, sections) → review/approval/export → hardening (RC1) → pilot readiness.
- **Effort** 758 pd most likely (P50 915, P80 1,009 with correlated uncertainty); +80 pd versus v1.0 from CN-2026-11-17.
- **Duration** (reference team S2, 4 FTE): plan 413 WD ≈ **42 sprints**; P50 492 WD ≈ 50 sprints; P80 546 WD ≈ 55 sprints. Balanced team S3 (6 FTE): plan 324 WD ≈ 33 sprints; P80 431 WD ≈ 44 sprints.
- **The plan is resource-bound.** The dependency critical path is 116 WD; the long poles are the single kernel engineer (until the walking skeleton and again in M4a, which now carries 50 pd of kernel zone work) and the single backend engineer (M2 and M5).
- **Gates that decide dates more than code does:** decision record (S01), library lock-in (end of M1), VER-22 inspection (end of M2), RC1 feature freeze, clinic availability for M7.

## 2. Milestones

### M0 — Foundations and decisions

| Item | Content |
|---|---|
| Goal | A repository where every later task lands in a fixed structure, with enforced standards, the persistence model, platform services and kernel contracts; all blocking decisions ratified |
| Scope (46 tasks, 84.5 pd ML) | XC-FND-01…06, -10, -11, -12; XC-PLT-13 (clinic modelling session — done 2026-11-17); XC-SHR-01, XC-SHR-03; XC-EXP-06, XC-EXP-08; FN-API-01/02, FN-AUD-01/06, FN-JOB-01…04, FN-BLB-01, FN-IAM-01…04, FN-KIO-01/06, FN-KFR-03, FN-KRP-02/03/04, FN-REV-06, FN-OPS-01/02/03/06 |
| Entry criteria | Planning deliverables accepted; GitHub organisation/repository available; team members named (OD-04) |
| Exit criteria | (1) XC-FND-01 countersigned (done 2026-11-17); (2) `docker compose up` brings up proxy, web, api, worker, postgres and storage fake; (3) all CI stages exist and block merges on seeded failures; (4) error catalogue `error/1` frozen (IDR-05); (5) login, session timeout, lockout, permission matrix and hash-chained audit pass VER-12/VER-13 integration tests; (6) job queue claim/lease/retry tests pass; (7) predicates agree 100 % with the rational oracle on T13; (8) X-06 and X-08 reports filed |
| Demo | Log in, see an empty case list; CI dashboard with all stages green |

### M1 — Kernel core and walking skeleton

| Item | Content |
|---|---|
| Goal | Prove the architecture end to end on synthetic phantoms; lock the library set |
| Scope (56 tasks, 147.9 pd) | XC-SHR-02 (BVH), FN-KIO-02/05/07, FN-KVL-01…07, FN-KFR-01, FN-KMS-01, FN-KOP-04/06, FN-KRP-01, FN-KEX-01/02, FN-AUD-02, FN-BLB-02, FN-UIX-02/03, FN-OPS-04/07, XC-FND-07/08/09, XC-EXP-01/02/07/BM01/LOCK, XC-WSK-01, stabilisation |
| Entry criteria | M0 exit; X-06 result available (numba or C++ fallback decided) |
| Exit criteria | (1) XC-WSK-01: phantom T2 STL → parse job → mm → test-only frame → closure → validity → hash-bound minimal approval → STL + manifest → re-import ≤ 1e-4 mm, in CI; (2) 100-run determinism on T9 references (VER-07); (3) self-intersection counts equal the CGAL oracle on VER-08 fixtures; (4) staging reachable over TLS with same-origin `/api`; (5) X-07 shows the app credential cannot overwrite/delete Storage objects (or IDR-07 fallback applied); (6) XC-EXP-LOCK signed; (7) viewer renders a display LOD |
| Demo | Upload a phantom in a dev page, watch jobs, view LOD, download released STL |

### M2 — Scan intake, configuration and data governance

| Item | Content |
|---|---|
| Goal | Real-world intake path with privacy controls complete enough for the VER-22 inspection |
| Scope (90 tasks, 180.7 pd) | FN-CAS-01…08 (+CAS-05 Should), FN-CFG-01…04, -07, -08, FN-SCN-01…12, FN-KIO-03/04, FN-KAN-01/02, FN-KCP-04, FN-KOP-01/02/03/05/13, FN-ANA-05, FN-IAM-05/06, FN-AUD-03/04/05, FN-BLB-03/04, FN-UIX-01/05/06, FN-OPS-05/10, XC-PLT-01/02, stabilisation |
| Entry criteria | M1 exit; Supabase project and staging host available |
| Exit criteria | (1) Case → consent → prescription → upload (STL/OBJ/PLY) → unit confirmation → integrity report → quality gate (with logged override) → recorded cleanup works on synthetic scans; (2) configuration drafts/publish/versioning with NOT_SET gates and production safety check; (3) erasure procedure and purge credential tested on staging; (4) backup + separate Storage backup + restore drill meet RPO/RTO 24 h; (5) read-access logging and controlled downloads (SEC-15/16); (6) **VER-22 inspection performed and recorded** (XC-PLT-01) → real-patient-data gate can open |
| Demo | Full intake of a synthetic scan with integrity gate and cleanup; audit log export |

### M3 — Anatomy and measurement

| Item | Content |
|---|---|
| Goal | Confirmed anatomical frame and explicit-definition measurements; first evidence from real scans |
| Scope (43 tasks, 88.0 pd) | FN-CFG-05/06, FN-KFR-02, FN-KAN-03, FN-KMS-02…06, FN-ANA-01…04, FN-ANA-06 (orientation fine-tuning, Should), FN-MEA-01…04, FN-MEA-05 (tape measure, Should), XC-EXP-02R (BM-02), XC-EXP-03, XC-EXP-05, stabilisation |
| Entry criteria | M2 exit for synthetic work; VER-22 record (EXT-01) and ≥ 3 clinic files (EXT-05) for the real-scan experiments |
| Exit criteria | (1) Landmarks snapped server-side with placement trail; frame computed, displayed and confirmed (det +1, laterality check); (2) CI, CVA, CVAI (both denominators, 30°/40° presets) and HC within DEC-025 tolerances on VER-01 phantoms; (3) no value without definition id + version; no thresholds/severity anywhere (FR-045 lint); (4) supersession on landmark/frame change; (5) BM-02 statistics recorded; X-03 confirms or challenges IDR-01 closure on real open scans |
| Demo | Place landmarks on a phantom, confirm the frame, compute and display measurements with definitions |

### M4a — Design workspace: operations

| Item | Content |
|---|---|
| Goal | Technician edits a positive mould through recorded, replayable operations with Rodin4D-level zone tools |
| Scope (40 tasks, 113.5 pd) | FN-KOP-07…12, FN-KOP-14 (free-form contour), FN-KOP-15 (profile editor), FN-KOP-16 (symmetric zone), FN-KOP-17/18 (Should), TSK-KOP-12-KG (whole-surface smoothing, IDR-38), FN-DES-01…05, XC-EXP-04, stabilisation |
| Entry criteria | M3 exit (confirmed frame is a precondition of design, FR-032) |
| Exit criteria | (1) Zones as circle/ellipse presets or free-form contours with editable control points; contour self-intersection refused; (2) profile presets plateau/peak and custom monotone curve; amplitude at plateau within e = 0.011 mm; (3) symmetric zone mirrors across the confirmed frame, linked parameters, laterality labels swapped; (4) global length (whole or two levels), circumference, offset, local smoothing with guard; (5) overlap refused with ZONE_OVERLAP_NOT_ALLOWED; out-of-range values need confirmation; (6) closure is the pinned terminal op; disable/re-enable restores the prior hash; (7) X-04 latency measured on a ~20-op reference history (CH-15) |
| Demo | Rebuild an observed Rodin4D-style history (zones, symmetric zones, radius, elongation, smoothing) on a phantom |

### M4b — Design workspace: live feedback

| Item | Content |
|---|---|
| Goal | Technician sees the effect of every edit without leaving the workspace |
| Scope (20 tasks, 42.4 pd) | FN-DES-06, FN-DES-07 (Should), FN-DES-08 live metrics, FN-KCP-01/02 (moved from M5), FN-UIX-04, FN-UIX-07 overlay, FN-UIX-08 2D sections (Should), FN-UIX-09 view cube (Should), stabilisation |
| Entry criteria | M4a core ops merged |
| Exit criteria | (1) Live panel: AP (anterior/posterior), ML, circumference, volume at a movable level with deltas vs prepared scan, equal to kernel measurements on VER-01 phantoms; (2) overlay with opacity and modified-region highlight from the latest regeneration; (3) sign convention identical in UI, manifest and report (VER-14); (4) 2D sections equal kernel sections |
| Demo | Edit a zone and watch metrics, overlay and sections update |

### M5 — Review, approval and export

| Item | Content |
|---|---|
| Goal | Complete WF-MVP-01 on synthetic data |
| Scope (20 tasks, 41.8 pd) | FN-KCP-03, FN-KFR-04, FN-REV-01…05, FN-EXP-01…03, stabilisation (FN-KCP-01/02 and FN-UIX-04 moved to M4b) |
| Entry criteria | M4b exit |
| Exit criteria | (1) Deviation map with per-zone statistics and validity panel ("geometric check" wording, FR-082); (2) approval binds geometry, parameters, scan, explicitly selected measurement set and prescription SHA-256; altering any binding makes export refuse; (3) export in the configured frame, manifest validates against schema, re-import ≤ 1e-4 mm, controlled download; (4) VER-03 laterality and VER-06 round-trip pass on phantoms |
| Demo | Whole workflow from case to released STL on a synthetic head |

### M6 — Hardening and system verification (RC1)

| Item | Content |
|---|---|
| Goal | Feature freeze of MVP-Core, system-level verification, performance evidence |
| Scope (14 tasks, 35.9 pd) | XC-REL-01, FN-RPT-01…03 (Should), FN-OPS-08/09/12, XC-EXP-BM03/BM04/BM05, XC-PLT-03, XC-PLT-10, stabilisation |
| Entry criteria | All MVP-Core tasks of M0–M5 closed (XC-REL-01 dependencies) |
| Exit criteria | (1) RC1 tagged; cut-line decision recorded for unfinished Should items; (2) E2E UC-02…UC-10 pass on the supported browsers (VER-11); (3) security suite + threat-model review pass, no CVSS ≥ 7.0 open (SD-04); (4) cross-host determinism (BM-03) recorded; (5) pilot-entry values N, S, LOD budget, time budgets set from evidence (XC-PLT-03); (6) legal licence review done |
| Demo | RC1 walkthrough on staging with the E2E report |

### M7 — Pilot readiness

| Item | Content |
|---|---|
| Goal | Go/no-go for the Saigak Orto pilot |
| Scope (9 tasks, 23.0 pd) | FN-OPS-11, XC-PLT-04…08, XC-PLT-11, XC-PLT-12, stabilisation |
| Entry criteria | M6 exit; clinic technician and production time booked (EXT-04, EXT-06) |
| Exit criteria | Pilot entry criteria of IMPLEMENTATION_PLAN §10: clinic configuration published (non test_only) and safety check passed; VER-02, VER-06 (Rodin4D Neo), VER-16 recorded; INT-08 clinic file coverage; VER-10 usability and VER-23 agreement computed against clinic thresholds (DEC-030); pilot deployment with restore drill; user guide and training record; go/no-go signed |
| Demo | Technician completes a real case on the pilot stack under observation |

## 3. Release candidate and cut line

- **RC1 (XC-REL-01)** depends on every MVP-Core task of M0–M5 (incl. M4a/M4b) (directly or through the milestone stabilisation tasks). Pilot work, final E2E and security suites, cross-host determinism and performance benchmarks start after RC1.
- At RC1 the cut line of MVP_SCOPE §4 is applied from the bottom (DES-07 templates first, FN-UIX-09 view cube last). No Core task depends on a Should task (checked), so cutting never breaks the build.
- Release tags: `v1.0.0-rc.N` during M6–M7, `v1.0.0` at the go/no-go (XC-PLT-11).

## 4. Staffing scenarios and milestone exits

Durations in working days from the start of M0 (sprint number = ⌈WD / 10⌉). "Plan" = most-likely efforts through the resource-constrained schedule; P50/P80 = Monte Carlo with correlated uncertainty.

| Milestone exit | S1 Lean 2.5 FTE — plan / P50 / P80 | S2 Reference 4 FTE — plan / P50 / P80 | S3 Balanced 6 FTE — plan / P50 / P80 |
|---|---|---|---|
| M0 | 65 / 79 / 87 WD (S07 / S08 / S09) | 55 / 66 / 74 WD (S06 / S07 / S08) | 36 / 46 / 52 WD (S04 / S05 / S06) |
| M1 | 188 / 223 / 249 (S19 / S23 / S25) | 145 / 179 / 196 (S15 / S18 / S20) | 97 / 120 / 134 (S10 / S13 / S14) |
| M2 | 273 / 326 / 363 (S28 / S33 / S37) | 198 / 243 / 264 (S20 / S25 / S27) | 140 / 170 / 189 (S14 / S17 / S19) |
| M3 | 350 / 418 / 464 (S35 / S42 / S47) | 234 / 282 / 310 (S24 / S29 / S31) | 176 / 213 / 238 (S18 / S22 / S24) |
| M4a | 410 / 487 / 542 (S41 / S49 / S55) | 304 / 361 / 400 (S31 / S37 / S41) | 213 / 258 / 287 (S22 / S26 / S29) |
| M4b | 457 / 545 / 608 (S46 / S55 / S61) | 318 / 378 / 418 (S32 / S38 / S42) | 242 / 290 / 322 (S25 / S30 / S33) |
| M5 | 513 / 610 / 680 (S52 / S61 / S69) | 350 / 417 / 464 (S35 / S42 / S47) | 262 / 314 / 350 (S27 / S32 / S36) |
| M6 | 572 / 680 / 757 (S58 / S68 / S76) | 383 / 456 / 506 (S39 / S46 / S51) | 294 / 351 / 392 (S30 / S36 / S40) |
| M7 (pilot go/no-go) | 607 / 723 / 802 (S61 / S73 / S81) | 413 / 492 / 546 (S42 / S50 / S55) | 324 / 385 / 431 (S33 / S39 / S44) |

Composition: S1 = 1 kernel, 1 full-stack, 0.5 QA/DevOps; S2 = 1 kernel, 1 backend, 1 frontend, 1 QA/DevOps; S3 = 2 kernel, 2 backend, 1 frontend, 1 QA/DevOps; each with external roles 2 × 0.5 FTE. Focus factor 0.7.

Pool finish in S2 (plan): kernel WD 316, backend 357, frontend 362, QA/DevOps 390, external 413 — the team stays loaded to the end; S2 is balanced but slow; S3 removes the kernel and backend bottlenecks.

## 5. Reference sprint plan (scenario S2, plan values)

Tasks are listed by the sprint in which they start; a task may run across sprints. The authoritative per-task sprint is the WBS column `ref_sprint_S2`; it is recalculated when the team or estimates change.

| Sprint | Milestones active | Tasks started | ML pd started | Main tasks started |
|---|---|---|---|---|
| S01 | M0 (M2 external) | 8 | 20.0 | XC-FND-05 schema, XC-FND-12 kernel contracts, XC-FND-10 docs, XC-FND-02 repo, XC-FND-01 decisions, XC-PLT-13 (done), XC-EXP-08, XC-PLT-02 |
| S02 | M0 | 7 | 21.0 | XC-SHR-01 predicates, XC-FND-03 CI, TSK-AUD-01-A audit chain, XC-FND-11 logging, XC-EXP-06 numba |
| S03 | M0, M1 | 12 | 21.0 | XC-FND-07 environments, TSK-IAM-01-B auth, XC-FND-06 API contract, XC-EXP-07 Supabase immutability |
| S04 | M0 | 7 | 17.5 | TSK-OPS-06-C fixtures, TSK-IAM-01-U login UI, XC-SHR-03 T13–T15, TSK-JOB-02-J worker |
| S05 | M0, M1 | 13 | 21.5 | XC-SHR-02 BVH, XC-FND-09 sandbox, TSK-API-01-A, TSK-JOB-04-J |
| S06 | M0, M1 | 12 | 25.0 | TSK-KVL-05-K self-intersection, XC-FND-08 Supabase adapter, TSK-REV-06-A, TSK-KIO-05-K |
| S07 | M1, M2 | 3 | 7.0 | TSK-CFG-01-B, TSK-UIX-03 gate/job status |
| S08 | M1, M2 | 6 | 25.5 | TSK-KRP-01-K replay, TSK-OPS-07-C oracle container, TSK-KVL-05-V, TSK-CFG-02-B |
| S09 | M1, M2 | 9 | 26.0 | TSK-CFG-01-U config editor, TSK-KVL-01-K, TSK-KRP-01-V, TSK-UIX-01-U shell |
| S10 | M1, M2 | 10 | 22.5 | TSK-CAS-08-O erasure, XC-EXP-01, XC-EXP-BM01, TSK-CFG-02-U |
| S11 | M1, M2 | 20 | 32.5 | TSK-OPS-05-O backup/restore, TSK-KMS-01-K, XC-PLT-01 VER-22, TSK-SCN-01-U |
| S12 | M1, M2 | 13 | 28.5 | TSK-UIX-02-U viewer, TSK-KOP-06-K closure, TSK-KVL-07-K |
| S13 | M1–M3 | 10 | 17.6 | TSK-KOP-06-V, XC-EXP-02, TSK-CFG-06-B |
| S14 | M1–M3, M6 | 19 | 33.5 | **XC-WSK-01 walking skeleton**, XC-EXP-LOCK, M1 stabilisation, TSK-CFG-05-B |
| S15 | M1–M4a | 8 | 19.3 | TSK-DES-03-J regeneration, TSK-KIO-03-K OBJ, TSK-CFG-05/06-U |
| S16 | M2, M4a, M4b | 12 | 20.5 | TSK-KIO-04-K PLY, TSK-KAN-01-K snap, TSK-SCN-02-J parse job |
| S17 | M2 | 15 | 24.5 | TSK-KOP-13-K guard, TSK-SCN-05 integrity job + panel, TSK-UIX-05-B |
| S18 | M2 | 11 | 31.3 | TSK-KOP-02-K hole filling (Should), TSK-UIX-05-U region selection, TSK-SCN-11-B |
| S19 | M2, M3 | 8 | 21.4 | TSK-SCN-11-U, M2 stabilisation, TSK-KOP-03-K (Should) |
| S20 | M2, M3, M4b | 10 | 21.5 | TSK-ANA-02 landmarks, TSK-KFR-02-K frame, TSK-MEA-05-B tape measure |
| S21 | M3, M4a, M5 | 14 | 22.0 | TSK-KMS-04 diagonals/CVA/CVAI, TSK-ANA-06-B orientation fine-tuning |
| S22 | M3, M4a, M4b, M6 | 13 | 25.3 | TSK-UIX-08-U 2D sections, TSK-MEA-01-B, XC-EXP-02R real scans |
| S23 | M3, M4b | 10 | 24.2 | **TSK-DES-08-B live metrics**, TSK-KAN-03-K, TSK-MEA-02-U |
| S24 | M3–M5 | 6 | 17.5 | TSK-KOP-10-K zones, TSK-DES-08-U, M3 stabilisation |
| S25 | M4a | 2 | 14.0 | **TSK-KOP-14-K free-form contour**, TSK-KOP-10-V |
| S26 | M4a | 5 | 20.0 | TSK-KOP-14-U contour editor, TSK-DES-02-B, TSK-KOP-14-V, TSK-KOP-15-K profile |
| S27 | M4a, M4b | 8 | 19.9 | TSK-KOP-16-K symmetric zone, TSK-KOP-15-U, TSK-KOP-09-K, TSK-DES-07-B |
| S28 | M4a | 7 | 19.2 | TSK-DES-02-U design workspace, XC-EXP-04 (~20-op history), M4a stabilisation |
| S29 | M4a | 5 | 14.4 | TSK-KOP-12-K smoothing, TSK-KOP-07-K offset, TSK-KOP-16-U |
| S30 | M4a, M4b | 5 | 10.0 | TSK-DES-07-U, TSK-KOP-18-K, TSK-KOP-17-K |
| S31 | M4a, M4b | 3 | 8.0 | TSK-KCP-01-K signed distance, TSK-KOP-12-KG whole-surface smoothing |
| S32 | M4b, M5 | 14 | 21.4 | TSK-REV-04-B approval, **TSK-UIX-07-U overlay**, TSK-REV-01-J review job |
| S33 | M5 | 2 | 9.0 | TSK-EXP-02-J export job, TSK-REV-04-U |
| S34 | M5 | 3 | 9.0 | TSK-REV-02-B, TSK-EXP-01-U/B |
| S35 | M5, M6 | 9 | 13.8 | TSK-REV-02-U, **XC-REL-01 RC1**, TSK-RPT-02-J (Should), M5 stabilisation |
| S36 | M6, M7 | 8 | 22.0 | TSK-OPS-12-C security, XC-PLT-07 physical verification, XC-PLT-12 guide, XC-EXP-BM04 |
| S37 | M6 | 1 | 8.0 | TSK-OPS-08-C E2E suite |
| S38 | M6 | 4 | 8.4 | XC-EXP-BM05, XC-EXP-BM03, XC-PLT-03 NFR values |
| S39 | M7 | 4 | 8.0 | XC-PLT-05 pilot deployment, XC-PLT-04 clinic configuration, XC-PLT-06 |
| S40 | M7 | 1 | 5.0 | XC-PLT-08 usability + agreement |
| S41–S42 | M7 | 1 | 1.0 | XC-PLT-11 go/no-go |

Observations: S07, S25, S31, S33–S34 start few tasks because a single engineer is busy with long tasks (backend in S07/S33, kernel zone work in S25/S31). M4a is kernel-heavy (50 pd): a second geometry engineer (S3) shortens it most. In S2 the live metrics (S23) start before the zone operations (S25) because they depend only on regeneration and sections.

## 6. Gate timeline (scenario S2, reference sprints)

| Gate | Task | Starts | Effect |
|---|---|---|---|
| Decision record ratified | XC-FND-01 | S01 | Releases previously blocked tasks |
| numba / image matrix evidence | XC-EXP-06, XC-EXP-08 | S01–S02 | Fixes kernel acceleration and Python/wheel matrix |
| Supabase immutability + backup | XC-EXP-07 | S03 | Decides IF-04 adapter behaviour (IDR-07 fallback) |
| Library lock-in | XC-EXP-LOCK | S14 | SOUP list frozen for MVP |
| Walking skeleton | XC-WSK-01 | S14 | Architecture proven end to end |
| VER-22 inspection | XC-PLT-01 | S11 (needs privacy specialist) | Opens real-patient-data gate |
| Real-scan evidence | XC-EXP-02R, -03, -05 | S22–S23 | N, S, n_max proposals; closure confirmation |
| RC1 feature freeze | XC-REL-01 | S35 | Starts system verification and pilot work |
| Pilot-entry values | XC-PLT-03 | S38 | NFR-01…04 set |
| Go/no-go | XC-PLT-11 | S41–S42 | v1.0.0 |

## 7. Converting to calendar dates (when resources are known)

1. Fix team composition (OD-04) and the start date of S01.
2. Re-run the generator with the real FTE per pool (and real focus factor after two sprints of velocity data).
3. Date of milestone exit = start date + WD (from §4 or the re-run), skipping public holidays and planned leave.
4. Commit externally to **P80**; track internally against P50.
5. Re-forecast at every milestone exit and whenever a re-planning trigger fires (IMPLEMENTATION_PLAN §10).

## 8. Re-planning triggers

| Trigger | Action |
|---|---|
| X-06 fails (numba not deterministic) | Switch inner loops to the C++/nanobind fallback; +5–10 pd kernel; re-run schedule |
| X-01 shows own BVH too slow | libigl for closest point (IDR-10 fallback); review TT-V scope for that path |
| X-02 shows self-intersection too slow on real scans | Incremental mode + time budget (SELF_INTERSECTION_TIMEOUT) or commercial CGAL licence decision |
| A CN-2026-11-17 tool turns out not to be used for helmets (informal check with technicians) | Drop the function to v1.1 before it starts; re-run the generator |
| X-03 shows frequent non-simple base contours | Re-open IDR-01/OQ-FS-37 handling; possible cleanup op addition |
| VER-22 late | Continue on synthetic data; M3 real-scan experiments and M7 move by the same delay |
| Velocity < 80 % of plan for two sprints | Apply cut line earlier; revise staffing |
| Clinic availability for M7 < planned | Hold RC; keep developers on Should items or v1.1 preparation |
