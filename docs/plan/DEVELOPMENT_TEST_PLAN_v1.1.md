# Development Test Plan v1.1 — Jude

| Field | Value |
|---|---|
| Document | DEVELOPMENT_TEST_PLAN_v1.1.md |
| Version / date | v1.1 · 2026-11-17 — CN-2026-11-17 applied (tests for new CAD functions, fixtures T16–T17, M4a/M4b); supersedes v1.0 |
| Status | Draft for ratification with IMPLEMENTATION_PLAN_v1.1 |
| Inputs | GEOMETRY_TESTING_STRATEGY_v1.0 (GTS: levels L0–L4, fixtures T1–T15, oracles, per-ALG test design, CI stages), 09_TEST_CASE_CATALOGUE v0.3 (128 TC), RTM v0.3 VER-01…VER-23, WBS v1.1 (`tests`, `test_levels`, `definition_of_done` columns) |
| Boundary | Tests establish software correctness (L0) and geometric validity (L1) and record manufacturing checks (L2). They are **not** evidence of clinical safety, fit or effectiveness (L3/L4 out of scope; FR-082). |

## 1. Summary

- Every one of the 338 scheduled tasks names its tests and test levels in the WBS; every catalogue test case (128/128 TC-*) is referenced by at least one task; every VER requirement (VER-01…VER-23 in MVP) is owned by named tasks (§8).
- Twelve test levels, each with an ID prefix, an owner, an environment and a CI stage (§2–§3).
- Merge is blocked by lint, unit/property, determinism, integration and contract stages; release is blocked by oracle, security and E2E stages (§5).
- Geometric verification (TT-V) is a separate task per kernel function, done by a QA engineer who did not write the kernel code (independence).

## 2. Test levels

| Level | Prefix | What it proves | Scope / environment | Owner | Tasks using it |
|---|---|---|---|---|---|
| Unit | UT-<FN> | Function behaves per FS spec on hand-built inputs | In-process; no DB/network | Author | 134 |
| Property-based | PT-<FN> | Invariants hold over generated inputs (hypothesis, fixed seed database) | In-process | Author | 53 |
| Geometric verification | GT-<FN> | Kernel output vs analytic truth within DEC-025 on fixtures T1–T15 | In-process; fixture files | QA (geometry), not author | 52 |
| Oracle comparison | ORC-<ALG> | Agreement with independent implementations (CGAL, PyMeshLab, trimesh, libigl, brute force, rational arithmetic) | Oracle container (GPL tools, never shipped) | QA (geometry) | 50 |
| Regression / golden | RT-<FN> | Byte-identical hashes for reference designs; no unintended change | CI determinism stage | QA | 72 |
| Integration | IT-<FN> | API + Postgres + storage fake + job runner work together; permissions, audit, transactions | Docker services in CI | Author | 93 |
| Component (UI) | CT-<FN> | UI components render states and gate lists correctly | vitest + Testing Library | Author | 51 |
| System / E2E | ST-*, E2E (UC-02…UC-10) | Complete workflows through the browser | Staging-like stack; Playwright browser matrix | QA | 51 tasks contribute E2E steps; 2 system tasks |
| Security | SEC-* | Authn/authz, CSRF, upload abuse, TLS, dependency and licence gates, threat-model items | CI security stage + staging | QA + engineering lead | 3 dedicated tasks + VER-12/13/21 rows |
| Performance / experiment | BM-*, X-* | Measured time/memory/determinism to set budgets and choose libraries | Dedicated hosts; recorded environment | Kernel + QA | 14 |
| Operational | OT-<FN> | Procedures (backup/restore, erasure, account review) produce the expected records | Staging dry run | QA / ops | 8 |
| Inspection / external record | INS-* | Documents, wording, privacy controls, physical verification | Human review with signed record | Named role | 11 |

## 3. Test ID conventions and traceability

| Item | Convention |
|---|---|
| Test IDs | `<PREFIX>-<FN-ID or ALG-ID>[-<n>]`, e.g. `UT-FN-KIO-02`, `GT-FN-KOP-06-3`, `ORC-ALG-11` |
| Catalogue IDs | `TC-<requirement>` kept verbatim from 09_TEST_CASE_CATALOGUE (v0.4 adds T13–T15 and UT IDs, XC-FND-10) |
| Markers in code | `@pytest.mark.fn("FN-KOP-06")`, `@pytest.mark.req("FR-173")`, `@pytest.mark.tc("TC-FR-173")`, `@pytest.mark.task("TSK-KOP-06-V")`; TS tests use `describe("FN-REV-04 …")` |
| Trace check | `tools/trace/check` (nightly): every MVP requirement → ≥ 1 task → ≥ 1 passing test; every TC in the catalogue has an implemented test by its milestone exit |
| Results | JUnit XML per stage + coverage + oracle/benchmark reports archived per commit; release evidence bundle per tag |

## 4. Task type → required tests

| Task type | Mandatory tests | Fixture / data | Pass criterion |
|---|---|---|---|
| TT-K kernel | UT + PT (+ catalogue TC IDs) | Hand-built meshes; hypothesis strategies with fixed seed | All pass; determinism 3 local runs identical |
| TT-V verification | GT + RT + ORC | T1–T15 per module (KIO: T3, T4 · KVL: T3, T13 · KFR: T5, T7 · KAN: T1, T14 · KMS: T1, T15 · KOP: T1, T2, T6, T8 · KCP: T1, T6 · KRP: T9 · KEX: T5, T10) | Within DEC-025 tolerances (e = 0.011 mm, perimeter 0.032 mm, file fidelity 1e-4 mm); invariants of GTS §6 hold; oracle disagreements triaged (analytic truth wins) |
| TT-B domain/API | UT + IT; VER-12 permission rows; VER-13 audit events | Seeded DB fixtures; storage fake | Allowed roles succeed, others 403; every mutation has exactly the expected audit event |
| TT-U UI | CT + an E2E step in FN-OPS-08 | Mock client responses; staging for E2E | Gate lists rendered from DS-24; wording lint clean |
| TT-J job | UT + IT incl. failure and retry paths | Job runner + Postgres + storage fake; fault injection | Atomic completion; no partial outputs; retries only for idempotent types |
| TT-A service | UT + IT | — | Error mapping per `error/1` |
| TT-O procedure | OT dry run + IT | Staging | Expected records produced; halts on first failed step |
| TT-C CI tooling | CI self-test | Seeded violation | Seeded violation fails the stage; clean tree passes |
| XC experiment | Protocol in TECHNICAL_OPEN_QUESTIONS §3 / PERFORMANCE_REQUIREMENTS §4 | BM-01 synthetic; BM-02 real only after VER-22 | Report complete; decision proposal recorded |

## 5. CI gates

| Stage | Contents | Runs | Blocks | Target duration |
|---|---|---|---|---|
| lint | ruff, mypy, eslint, tsc, wording lint (FN-OPS-01), import-linter, schema checks | Every PR | Merge | ≤ 5 min |
| unit | UT + PT (kernel, domain, web components) | Every PR | Merge | ≤ 10 min |
| determinism | T9 golden hashes on every PR; 100-run determinism nightly | PR + nightly | Merge | ≤ 10 min (PR) |
| integration | IT with Postgres + storage fake + job runner; VER-12 permission matrix; VER-13 audit completeness | Every PR | Merge | ≤ 15 min |
| contract | OpenAPI and JSON Schema diff (additive-only in v1); client regeneration | Every PR | Merge | ≤ 2 min |
| oracle | ORC-* in the oracle container | Nightly + PRs labelled kernel | Release | ≤ 60 min |
| security | Dependency scan (CVSS ≥ 7.0), licence allow-list + SOUP, secret scan, upload-abuse fixtures, TLS checks (staging) | Nightly + release | Release | ≤ 20 min |
| e2e | Playwright UC-02…UC-10 on the browser matrix (EXT-02) | Nightly + release | Release | ≤ 45 min |
| performance | BM-01 trend (report-only until XC-PLT-03 sets budgets; then budget breaches fail release) | Weekly | Report → Release after M6 | — |

## 6. Coverage and quality targets

| Metric | Target | Applies from |
|---|---|---|
| Line / branch coverage, `jude_kernel` | ≥ 95 % / ≥ 90 % | M1 |
| Line / branch coverage, `jude_api`, `jude_worker` | ≥ 85 % / ≥ 75 % | M2 |
| Component coverage, `apps/web/src/features` | ≥ 70 % lines | M3 |
| Requirements with a passing test (MVP-Core) | 100 % at RC1 | M6 |
| Catalogue TC implemented | 100 % of TC whose function is in a closed milestone | Each milestone exit |
| Determinism | 1 distinct hash per T9 design over 100 regenerations (VER-07) | M1 |
| Open P1 defects at milestone exit | 0 | Every milestone |
| Flaky tests | Quarantined within 1 day, fixed or removed within 1 sprint; never auto-retried in determinism stage | Always |

Coverage is a floor, not a goal: TT-V acceptance is by fixtures, invariants and oracle agreement, not by percentage.

## 7. Fixtures and oracles

| Set | Content | Generator task |
|---|---|---|
| T1 | Analytic phantoms (icospheres R = 75 mm s = 4…8, ellipsoids with known CI, asymmetric ellipsoid, torus) | TSK-OPS-06-C |
| T2 | Open head-like surfaces for closure | TSK-OPS-06-C |
| T3 | Defect catalogue (holes, duplicates, flips, non-manifold, self-intersections, ghost layers, components, degenerates, corrupt/empty/oversize/face-bomb files) | TSK-OPS-06-C |
| T4 | Same object in binary/ASCII STL, OBJ (quads, negative indices), PLY ASCII/LE/BE | TSK-OPS-06-C |
| T5 / T6 / T7 | Laterality object; sign-convention sphere; metamorphic exact transforms | TSK-OPS-06-C |
| T8 | Property-based zones/magnitudes (hypothesis database, fixed seed) | TSK-OPS-06-C |
| T9 | Ten reference designs (golden hashes) | TSK-OPS-04-C |
| T10 | Export round-trip with corruption injection | TSK-OPS-06-C |
| T11 | Physical phantom (calliper/CMM) | XC-PLT-07 |
| T12 | ≥ 3 real clinic scans per format — only after VER-22, only on staging/pilot, never in the repository | XC-EXP-02R |
| T13 / T14 / T15 | Adversarial predicate inputs; tie fixtures; contour shapes | XC-SHR-03 |
| T16 (CN-2026-11-17) | Free-form zone contours on sphere/ellipsoid phantoms: convex, concave, near-self-touching, self-intersecting (must be refused), crossing the base plane | TSK-KOP-14-V |
| T17 (CN-2026-11-17) | Transition profiles: plateau, peak, custom monotone and non-monotone point sets; ~20-op reference history mirroring an observed Rodin4D design (CH-15, added to T9) | TSK-KOP-15-V, XC-EXP-04 |

Oracles never share code with production (GTS §3): CGAL PMP and PyMeshLab (CI container only), trimesh, numpy-stl, mapbox-earcut, libigl, brute-force O(n²) references, Python `fractions` for exact predicates.

## 8. Verification requirements → owning tasks

| VER | Title | Owning tasks (WBS) | Milestone of first pass |
|---|---|---|---|
| VER-01 | Synthetic phantom suite | TSK-OPS-06-C, XC-SHR-03, TSK-OPS-07-C, all TT-V of KMS/KOP | M1 (partial), M3 (measurements) |
| VER-02 | Physical phantom check | TSK-OPS-11-O, XC-PLT-07 | M7 |
| VER-03 | Laterality test object | TSK-OPS-06-C, TSK-KIO-07-V, TSK-KFR-04-V | M5 |
| VER-04 | Jude vs Rodin4D comparison (Should) | TSK-OPS-09-O, TSK-OPS-11-O, XC-PLT-07 | M7 |
| VER-06 | Export round-trip | TSK-KIO-07-K/V, XC-WSK-01, TSK-OPS-11-O, XC-PLT-07 | M1 (phantom), M7 (Neo) |
| VER-07 | Determinism | TSK-KRP-01/02-K/V, TSK-OPS-04-C, XC-FND-03, XC-EXP-BM03 | M1 (one host), M6 (cross-host) |
| VER-08 | Defect mesh catalogue | TSK-OPS-06-C, TSK-OPS-07-C, XC-SHR-03, XC-EXP-02, TT-V of KVL | M1 |
| VER-09 | Wording and localisation lint | TSK-OPS-01-C (+ every TT-U DoD) | M0 |
| VER-10 | Technician usability test | TSK-OPS-09-O, XC-PLT-08 | M7 |
| VER-11 | Browser/hardware E2E suite | TSK-OPS-08-C | M6 |
| VER-12 | Permission and gate tests | TSK-OPS-12-C, TSK-OPS-10-O, every TT-B DoD | M0 onwards |
| VER-13 | Audit completeness | TSK-OPS-12-C, TSK-OPS-10-O, every TT-B DoD | M0 onwards |
| VER-14 | Sign-convention test object | TSK-DES-06-B/U, TSK-OPS-06-C, TSK-KOP-10-V, TSK-KOP-14-V, TSK-KOP-16-V | M4a/M4b |
| VER-15 | Positive closure verification | TSK-KOP-06-K/V, XC-WSK-01, XC-EXP-03 | M1 (synthetic), M3 (real) |
| VER-16 | Physical positive vs exported STL | TSK-OPS-11-O, XC-PLT-07 | M7 |
| VER-20 | Functional test coverage | XC-FND-02/03/04, stabilisation tasks, all tasks' DoD | Every milestone |
| VER-21 | Security test suite | TSK-OPS-12-C, TSK-OPS-10-O | M6 |
| VER-22 | Privacy controls inspection | TSK-OPS-10-O, TSK-CFG-08-B/U, XC-PLT-01 | M2 |
| VER-23 | Agreement with manual measurements | TSK-OPS-09-O, XC-PLT-08 | M7 |

## 9. Milestone test entry and exit criteria

| Milestone | Entry (test) | Exit (test) |
|---|---|---|
| M0 | CI skeleton exists | All merge stages active and self-tested; VER-09 lint active; VER-12/13 suites running on platform endpoints; T13 predicate agreement 100 % |
| M1 | M0 exit | Walking-skeleton system test green in CI; VER-07 on one host; VER-08 counts equal oracle; VER-15 on T2; kernel coverage targets met |
| M2 | M1 exit | Intake/gate/cleanup IT + CT green; restore drill OT passed; VER-22 inspection record; upload-abuse fixtures pass |
| M3 | M2 exit (+ VER-22 for real-scan tests) | VER-01 measurement phantoms within tolerance; definition-provenance tests; BM-02 report |
| M4a | M3 exit | T8 + T16 property tests (valid or explicit rejection); profile tests T17 (amplitude within e, no overshoot); symmetric-zone mirror test (reflection of contour within e, laterality labels swapped, refused without confirmed frame); disable/re-enable hash restoration; X-04 on the ~20-op history |
| M4b | M4a exit | VER-14 sign convention; live metrics equal kernel measurements on VER-01 phantoms (DEC-025); overlay highlight equals vertices with non-zero deviation; 2D sections equal ALG-23 contours |
| M5 | M4b exit | Approval binding tamper tests (each of 5 bindings); VER-03 laterality; VER-06 round-trip on phantoms |
| M6 | RC1 tagged | E2E (VER-11) on supported browsers; VER-21 security suite; cross-host BM-03; no CVSS ≥ 7.0; trace check 100 % for MVP-Core |
| M7 | M6 exit + EXT-04/06 | VER-02, VER-06 (Neo), VER-16, VER-10, VER-23 records; pilot smoke + restore drill on pilot stack |

## 9a. Tests for CN-2026-11-17 functions

| Function | Proposed requirement | Key tests | Fixtures |
|---|---|---|---|
| FN-KOP-14 Free-form zone contour | FR-183 | UT/PT region membership on full mesh; GT vertices outside contour+transition bit-identical; self-intersecting contour → ZONE_CONTOUR_INVALID; anchors resolved server-side | T16, T8 |
| FN-KOP-15 Parametric profile | FR-184 | UT presets C¹; PT custom curve monotone (no overshoot); GT plateau amplitude within e = 0.011 mm; profile params change params_sha | T17 |
| FN-KOP-16 Symmetric zone | FR-185 | GT mirror equals reflection across mid-sagittal plane within e; linked edit propagation; FRAME_NOT_CONFIRMED refusal; no reflection applied to stored geometry (SAF-03) | T5, T6, T16 |
| FN-DES-08 Live design metrics | FR-186 | IT values equal FN-KMS-01/03/05 + volume (ALG-12) on VER-01 phantoms; deltas vs prepared scan at same level; wording lint (no thresholds) | T1 |
| FN-UIX-07 Overlay | FR-187 | CT opacity 0–100 %; highlight set equals non-zero deviation vertices of latest regeneration | T1, T6 |
| FN-UIX-08 2D sections | FR-188 | CT contours equal ALG-23 output at the level (snapshot) | T1, T15 |
| FN-KOP-17 Two-level elongation | FR-189 | GT band extent change within 2e; outside band rigid translation; Δ = 0 identity | T1 |
| FN-KOP-18 In-zone filtering | FR-190 | GT vertices outside zone+transition bit-identical | T1 (noisy) |
| FN-MEA-05 Tape measure | FR-191 | UT straight distance exact on anchors; GT along-section length within 0.032 mm | T1 |
| FN-ANA-06 Orientation fine-tuning | FR-192 | UT det +1, reflection refused, reset returns landmark frame | T5, T7 |
| FN-UIX-09 View cube | FR-193 | CT camera directions equal frame axes | — |
| TSK-KOP-12-KG Whole-surface smoothing (IDR-38) | FR-179 | GT closure faces unchanged; deviation report produced | T1 (noisy) |

## 10. Regression policy

- Golden hashes per kernel image (T9) are updated only in a PR that bumps `op_version` and/or `kernel_version` and states why; reviewer from CODEOWNERS required.
- Any dependency upgrade on the kernel path runs the full determinism + oracle suite before merge (R-29).
- Every fixed defect gets a regression test at the lowest level that reproduces it.
- Stored designs from earlier releases are replayed in the nightly determinism job against their recorded kernel image (TQ-15/IDR-19).

## 11. Defect management

| Severity | Definition | Response |
|---|---|---|
| P1 | Wrong geometry/measurement/approval binding/audit/permission behaviour; data loss; security issue; determinism break | Stop the line: fix before new feature work in that area; milestone cannot exit |
| P2 | Functional defect with workaround; wrong wording/localisation | Fix within the sprint |
| P3 | Cosmetic, minor usability | Backlog, triaged at milestone exit |

Defects are GitHub issues with task/function/requirement IDs, reproduction fixture, environment (image digest) and severity; each closes with a linked test.

## 12. Test effort

Test effort is part of every task estimate (DEVELOPMENT_STANDARDS DoD) plus dedicated items: geometric verification tasks 65.5 pd, CI/test tooling 29.0 pd, experiments and benchmarks 34.5 pd, stabilisation 45.8 pd (most likely, ideal person-days; IMPLEMENTATION_PLAN §8.4).
