# Technical Open Questions v1.0

| Field | Value |
|---|---|
| Document | TECHNICAL_OPEN_QUESTIONS_v1.0.md |
| Version / date | v1.0 · 2026-11-15 |
| Status | Draft v1.0 for review — engineering proposal. **Not approved**; no decision in this set is final until signed by the engineering lead (ADR/TD status "Proposed"). |
| Blocking levels | B1 = blocks implementation of the named functions or real-data use; B2 = blocks library lock-in / baseline sign-off; Pilot-entry = needed before pilot; NB = non-blocking (default implemented and replaceable) |

## 1. New technical questions

| ID | Question | Why it matters | Options | Recommendation (not a decision) | Owner | Blocking | Functions | Needed by |
|---|---|---|---|---|---|---|---|---|
| TQ-01 | Is the Functional Specification v1.0 approved, and by whom? Its header says "Draft for review"; the brief states the stage is complete; no decision record after DR-2026-11-12 exists. | Technical design must not rest on unconfirmed baselines | (a) record approval (date, role); (b) treat FS as draft and keep TD v1.0 draft | Record an approval note for FS v1.0 and this TD set in the next decision record | Product owner + engineering lead | B2 — blocks baseline sign-off of this TD set, not planning | All | Before Implementation Planning sign-off |
| TQ-02 | Where do C3 (API), C4 (worker) and C0 (proxy) run relative to the Supabase project (same region? provider?) | Latency, data residency (LQ-03), sandboxing features | Container host near the Supabase region; clinic server | Container host in the same region as the Supabase project; record in deployment record | Engineering lead | B1 — blocks deployment and real data (= OQ-FS-08) | FN-BLB-*, FN-OPS-05, FN-SCN-02 | Before M1 |
| TQ-03 | Can Supabase Storage enforce no-overwrite / no-delete for the application credential while allowing a separate purge credential, and is a separate daily Storage backup in place? | INV-02, FR-011, SEC-08, SEC-11; Supabase DB backups exclude Storage objects | Bucket policies + separate service keys; or S3-compatible storage elsewhere | Run X-07 and record result; implement separate encrypted Storage backup | Engineering lead | B1 — blocks real data (part of OQ-FS-08, MA-05) | FN-BLB-01, FN-BLB-04, FN-OPS-05 | Before first real scan |
| TQ-04 | Keep own session auth (ADR-014) or use Supabase Auth? | Platform offers auth; ADR-014 predates SD-05 | Own; Supabase Auth | Own (TD-14) unless SSO is required | Engineering lead | NB | FN-IAM-* | M0 |
| TQ-05 | Which spatial-query implementation (closest point, ray cast): libigl, Open3D or own numba BVH? | Determinism, tie handling, licence, SOUP size | libigl; Open3D; own | Decide by X-01 | Engineering lead | B2 — library lock-in | FN-KAN-01, FN-KAN-03, FN-KCP-01, FN-KCP-03 | M1 |
| TQ-06 | Windowed-sinc smoothing: VTK filter or own implementation? | VTK is a large SOUP item; parameters must match FR-179 semantics | VTK; own | Own if VTK not otherwise selected; else VTK after X-01 | Engineering lead | B2 | FN-KOP-12 | M4 |
| TQ-07 | LOD decimation library: fast-simplification, meshoptimizer (Python alpha) or own QEM? | Display only, but determinism helps caching | fast-simplification; meshoptimizer; own | Decide by X-01 | Engineering lead | NB | FN-KOP-04 | M1 |
| TQ-08 | Cap triangulation: own exact ear clipping or mapbox-earcut? | Robustness on near-collinear contours | Own; earcut | Own (TD-12); earcut as oracle | Engineering lead | NB | FN-KOP-06.4 | M4 |
| TQ-09 | Python version and wheel matrix (3.12 vs 3.13; x86-64 vs arm64) for numpy 2.5, scipy 1.18, numba, libigl/Open3D, WeasyPrint system libs | numpy 2.5 and scipy 1.18 require ≥ 3.12 (PyPI); other wheels unverified | 3.12; 3.13 | Build the image matrix (X-08) and fix the version in the SOUP list | Engineering lead | B2 | All worker functions | M0 |
| TQ-10 | Deviation image renderer for the PDF (OQ-FS-24) | No component defined (GAP-M09) | VTK off-screen; own rasteriser; headless browser | Own rasteriser (TD-18) | Engineering lead | NB | FN-RPT-02 | M6 |
| TQ-11 | Adopt numba (fastmath off, parallel off) for kernel inner loops? | Performance of ALG-11/33/34/40 in pure Python is insufficient for 10^5–10^6 faces [H] | numba; C++ extension | Decide by X-06 | Engineering lead | B2 | FN-KVL-05, FN-KAN-01, FN-KCP-01 | M1 |
| TQ-12 | Hole-filling loop size cap n_max (O(n³) DP) | Bounds worst-case time; value depends on real hole sizes | Fixed engineering constant from BM-02; configuration key | Engineering constant from BM-02 hole statistics | Engineering lead | NB | FN-KOP-02 | M2 |
| TQ-13 | Mesh size N, upload cap S, face cap, time budgets (= OQ-FS-29) | All performance requirements are TBD | Clinic IT inventory + BM-02 | Pilot-entry values PE-05…07 from BM-01/BM-02 | Clinic IT + engineering lead | Pilot-entry | FN-SCN-01, FN-DES-03, FN-UIX-02, FN-OPS-08 | M6 |
| TQ-14 | Supported browsers and minimum client hardware (NFR-01/02) | Viewer budgets | — | Inventory clinic PCs (OQ-A2) | Clinic IT | Pilot-entry | FN-UIX-02, FN-OPS-08 | M6 |
| TQ-15 | Retention of kernel container images for reproducing approved designs (ADR-010) | Old approvals need old kernels | Retention = clinic contract retention; shorter | Equal to case retention (SD-06) | Engineering lead + privacy specialist | NB | FN-KRP-01, FN-OPS-04 | M5 |
| TQ-16 | Accepted fallback if bit-exact cross-host determinism fails | ADR-010 revisit | Documented tolerance; pin host CPU family | Decide only after BM-03 evidence | Engineering lead + QA lead | NB | FN-KRP-02, FN-OPS-04 | M5 |
| TQ-17 | OBJ polygons k > 3: triangulation rule | Affects imported topology and hashes | Fan; ear clipping in best-fit plane | Fan if convex, ear clipping otherwise (ALG-03) | Engineering lead | NB | FN-KIO-03 | M1 |
| TQ-18 | Contour/diagonal non-convex rule: which intersections define a diagonal when a line meets the contour more than twice? | CVA reproducibility on irregular contours | Outermost hits; first hits from centre | Outermost hits; add to definition record together with OQ-FS-03 | Product owner + clinic technician | B1 with OQ-FS-03 | FN-KMS-04 | Before M2 |
| TQ-19 | Minimum transition width T for zones (C⁰ step allowed?) | T = 0 creates a step and fold risk | Allow 0; minimum engineering constant; clinic range | Clinic range in magnitude_ranges (SAF-07 confirmation) | Clinic technician | NB | FN-KOP-10 | M4 |
| TQ-20 | Worker sandbox mechanism on the chosen host (rlimits only, seccomp profile, gVisor) | SEC-07 untrusted parsing | rlimits + container hardening; seccomp; gVisor | Container hardening + rlimits in a child process; seccomp if host supports | Engineering lead | B1 with OQ-FS-08 | FN-SCN-02.1 | M1 |
| TQ-21 | Use trimesh 5.x anywhere in production? | 07 assumed 4.x; 5.x released 2026-11-12 | Oracle only; production utilities | Oracle only (TD-03) | Engineering lead | NB | FN-OPS-07 | M0 |
| TQ-22 | Incremental self-intersection time budget per op | Interactive editing (NFR-04 TBD) | — | Measure in X-02 and set with NFR-04 | Engineering lead | Pilot-entry | FN-KOP-13 | M4 |
| TQ-23 | Ship matplotlib (PSF-based licence) or keep it to analytics tooling? | Not on ADR-011 allow-list | Ship; tooling only | Tooling only (FN-OPS-09 notebooks) | Engineering lead | NB | FN-OPS-09, FN-RPT-02 | M6 |
| TQ-24 | Legal review of the licence allow-list and SOUP list (OQ-G6) | Engineering cannot conclude legal compliance | — | External review before pilot | Product owner | Pilot-entry | FN-OPS-02 | M6 |
| TQ-25 | Hash/cache container format jude-arr/1 vs .npy/.npz (FS FN-SCN-02 output format says npz) | Canonical bytes for blob addressing; .npz embeds zip timestamps | Own header; numpy .npy | Own minimal header (no pickle, no zip metadata timestamps) | Engineering lead | NB | DS-01, FN-BLB-01 | M0 |
| TQ-26 | Guard strictness for normal flips near zero (\|n·n'\| ≈ 0) | False rejections vs missed folds | Threshold 0 with exact fallback; small negative tolerance | Threshold 0 + exact orient3d fallback | Engineering lead | NB | FN-KOP-13 | M4 |

## 2. Inherited blocking functional questions (OPEN_FUNCTIONAL_QUESTIONS_v1.0)

| ID | Topic | Design impact |
|---|---|---|
| OQ-FS-01 | Closure position in the op sequence | TD-07 assumes pinned terminal op; FN-KOP-06/FN-KRP-01 not released |
| OQ-FS-02 | Measurement formula representation | DS-10 proposes enumerated formula types |
| OQ-FS-03 | Contour selection, diagonal centre, angle reference | ALG-35/37 support all options; DS-10 fields proposed |
| OQ-FS-04 | Measurement set bound at approval | DS-20 field measurement_set_id semantics |
| OQ-FS-06 | Error-code catalogue | TD-22 API freeze |
| OQ-FS-07 | Erasure vs immutability | DS-18 split core/summary; IF-04 purge credential |
| OQ-FS-08 | Supabase mapping | TD-13, TQ-02/03/20 |

Non-blocking inherited questions OQ-FS-05, -09…-38 remain as listed in OPEN_FUNCTIONAL_QUESTIONS_v1.0 and are referenced from the function specifications where they apply.

## 3. Experiments

| ID | Experiment | Data | Decides |
|---|---|---|---|
| X-01 | Determinism and tie handling of candidate libraries (closest point/BVH: libigl, Open3D, own; decimation: fast-simplification, meshoptimizer, VTK; smoothing: VTK vs own) | 100 runs × 2 hosts on BM-01 phantoms; tie fixtures (equidistant faces) | TD-03, TD-11, TQ-05, TQ-06, TQ-07 |
| X-02 | Own self-intersection detector vs CGAL oracle; time vs m; incremental mode | VER-08 fixtures + ghost layers; then ≥ 3 real scans (after VER-22) | TD-05, TQ-22 |
| X-03 | Closure option A on real open scans (holes above plane, non-simple contours frequency) | BL-134 scans | OQ-FS-01, OQ-FS-37, TD-07 |
| X-04 | Regeneration latency with per-op cache | BM-07 on synthetic designs | NFR-04 proposal, TD-01 |
| X-05 | Hole-filling quality and cost on clinic scans | BL-134 | TD-06, TQ-12 |
| X-06 | numba determinism (fastmath off) and warm-up cost on two hosts | BM-01 kernels | TD-02, TQ-11 |
| X-07 | Supabase Storage immutability and backup verification | Scratch project: try overwrite/delete with app credential; restore drill from separate backup | TD-13, TQ-03, MA-05 |
| X-08 | Container image build matrix (Python 3.12/3.13 × x86-64/arm64) | CI build of worker image with all candidate wheels | TQ-09 |

## 4. Blocking list (consolidated)

- OQ-FS-01
- OQ-FS-02
- OQ-FS-03
- OQ-FS-04
- OQ-FS-06
- OQ-FS-07
- OQ-FS-08
- TQ-02 (B1 — blocks deployment and real data (= OQ-FS-08))
- TQ-03 (B1 — blocks real data (part of OQ-FS-08, MA-05))
- TQ-18 (B1 with OQ-FS-03)
- TQ-20 (B1 with OQ-FS-08)
- TQ-01 (B2 — blocks baseline sign-off of this TD set, not planning)
- TQ-05 (B2 — library lock-in)
- TQ-06 (B2)
- TQ-09 (B2)
- TQ-11 (B2)
