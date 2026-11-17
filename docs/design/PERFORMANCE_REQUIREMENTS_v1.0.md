# Performance and Scalability Requirements v1.0

| Field | Value |
|---|---|
| Document | PERFORMANCE_REQUIREMENTS_v1.0.md |
| Version / date | v1.0 · 2026-11-15 |
| Status | Draft v1.0 for review — engineering proposal. **Not approved**; no decision in this set is final until signed by the engineering lead (ADR/TD status "Proposed"). |
| Rule | No numeric limit is invented. Values are either approved (DR-2026-11-12, DEC-025) or TBD with a measurement method. No benchmark was run for this document; complexity statements are asymptotic or labelled [H]. |

## 1. Metrics

| ID | Metric | Scope | Unit | Value | Status | Method |
|---|---|---|---|---|---|---|
| PM-01 | Maximum upload size S | FN-SCN-01, C0 proxy, API | MB | TBD (NFR-03, OQ-FS-29) | Not set | BM-02 file-size distribution of clinic exports + headroom; decided by owner |
| PM-02 | Maximum triangle count N (accepted for design) | FN-KIO-05, FN-SCN-02 | faces | TBD (NFR-03) | Not set | BM-02 face-count distribution; BM-01 scaling curves |
| PM-03 | Face-count hard cap for parsing (face-bomb protection) | FN-KIO-02…05 | faces | TBD (SEC-07); must be ≥ N | Not set | Memory model: ~(24 B·3 soup + 24 B V + 12 B F) per face bound in worker RAM |
| PM-04 | Parse + import time p95 at N | FN-SCN-02 | s | TBD | Not set | BM-01 (synthetic) and BM-02 (real) |
| PM-05 | Integrity report time p95 at N (incl. self-intersection) | FN-SCN-05 | s | TBD | Not set | BM-01 with ghost-layer fixtures; X-02 |
| PM-06 | Regeneration latency p95 for one zone edit (T_regen) | FN-DES-03, NFR-04 | s | TBD (NFR-04) | Not set | X-04 with per-op cache, BM-07 |
| PM-07 | Review job time p95 (validity + deviation) | FN-REV-01 | s | TBD | Not set | BM-07 |
| PM-08 | Export job time p95 | FN-EXP-02 | s | TBD | Not set | BM-07 |
| PM-09 | Viewer: time to first render and interactive frame rate on min-spec client | FN-UIX-02 | s; fps | TBD (NFR-01/02) | Not set | BM-04 on clinic PCs |
| PM-10 | Display LOD face budget | FN-KOP-04 | faces | TBD | Not set | BM-04 frame-rate vs faces curve |
| PM-11 | Worker peak memory per job at N | C4 | MiB | TBD | Not set | BM-06 (RSS sampling) |
| PM-12 | Concurrent users | Whole system | users | ≤ 5 assumed (A-16) | Assumption | Clinic confirmation |
| PM-13 | Session idle timeout | FN-IAM-02 | min | 30 (SD-02) | Approved (DR-2026-11-12) | TC-SEC-06 |
| PM-14 | Login lockout | FN-IAM-01.2 | — | 5 failures / 15 min → 15 min lock (SD-01) | Approved | TC-SEC-05 |
| PM-15 | Backup RPO / RTO | FN-OPS-05 | h | 24 / 24 (SD-03) | Approved | TC-SEC-08 restore test |
| PM-16 | Determinism | FN-KRP-01, FN-OPS-04 | distinct hashes | 1 per design over 100 regenerations (QAS-01, VER-07) | Approved requirement | BM-03 |
| PM-17 | Geometric accuracy | Kernel | mm | e = 0.011; perimeter 0.032; file fidelity 1e-4 (DEC-025) | Approved | VER-01 phantoms |
| PM-18 | Job claim latency (queue → running) | FN-JOB-02 | ms | TBD (poll interval ≤ 250 ms proposed in ADR-007) | Proposal | BM-05 |
| PM-19 | Audit append overhead per mutation | FN-AUD-01 | ms | TBD | Not set | BM-05 |
| PM-20 | Upload throughput clinic → server | FN-SCN-01 | MB/s | TBD (OQ-A2) | Not set | BM-05 at clinic network |

## 2. Computational complexity of the design path

| ALG | Name | Complexity |
|---|---|---|
| ALG-01 | File format detection by signature | O(1) on the 4 KiB prefix |
| ALG-02 | STL parsing (binary and ASCII) | Binary O(n) vectorised; ASCII O(bytes) tokenizer-bound [H] |
| ALG-03 | OBJ parsing with polygon triangulation | O(bytes) + Σ O(k²) for ear clipping of k-gons |
| ALG-04 | PLY parsing (ASCII, binary LE/BE) | O(bytes) |
| ALG-05 | Indexed mesh construction with exact vertex merge | O(n log n) sort |
| ALG-06 | Binary STL writer and independent re-read comparison | O(m) |
| ALG-07 | Edge topology, boundary loops and non-manifold detection | O(m log m) |
| ALG-08 | Degenerate face detection | O(m) |
| ALG-09 | Connected components | O(m) |
| ALG-10 | Orientation consistency, outward test and recorded re-orientation | O(m) |
| ALG-11 | Self-intersection detection with exact predicates | O(m log m + k) expected for BVH with k candidate pairs [N]; worst case O(m²) for pathological overlap (ghost layers produce many candidates) [H] |
| ALG-12 | Watertightness, signed volume and bounding box | O(m) |
| ALG-13 | Composite solid validity (validate.solid) | Dominated by ALG-11 |
| ALG-14 | Vertex normal estimation (angle-weighted) | O(m) |
| ALG-15 | Recorded face removal and compaction (mesh cleaning) | O(m + n) |
| ALG-16 | Hole filling: minimum-weight triangulation + refinement (+ optional fairing) | O(n³) per loop (DP) + sparse solve O(p^1.5) typical for p patch vertices [N] |
| ALG-17 | Quadric error metric decimation with topology constraints | O(m log m) |
| ALG-18 | Local windowed-sinc smoothing (Taubin/VTK style) with blended rim | O(N · edges in region) |
| ALG-22 | Mesh repair policy (explicit recorded repair only) | Sum of ops |
| ALG-23 | Plane section to contours with symbolic tie rule | O(m) |
| ALG-24 | Positive closure: plane cut + prism wall + planar cap (option A) | O(m) cut + O(k²) cap for k contour vertices (ear clipping) |
| ALG-25 | Polygon simplicity test and ear-clipping triangulation | Simplicity O(k log k) (sweep) or O(k²); ear clipping O(k²) worst case |
| ALG-26 | Uniform vertex-normal offset with fold check | O(n) + guard |
| ALG-30 | Unit scaling to millimetres | O(n) |
| ALG-31 | Anatomical frame construction from named landmarks | O(k) for k landmarks |
| ALG-32 | Rigid transform algebra and reflection guard | O(n) to apply |
| ALG-33 | BVH closest point, anchor snap and anchor evaluation | Build O(m log m); query O(log m) expected [N] |
| ALG-34 | Sector coverage by ray casting | O(r log m) for r rays |
| ALG-35 | Measurement contour selection | O(Σk) |
| ALG-36 | Cranial index (CI) on a contour | O(k) |
| ALG-37 | Diagonals, CVA and CVAI variants | O(k) |
| ALG-38 | Head circumference (HC) as contour perimeter | O(k) |
| ALG-39 | Synthetic-surface contact flag | O(k) |
| ALG-40 | Signed distance field with angle-weighted pseudonormal sign | O(n log m) |
| ALG-41 | Deviation statistics and one-sided vertex-to-surface Hausdorff | O(n) |
| ALG-43 | Region segmentation (MVP: technician-defined regions) | O(selection · log m) |
| ALG-46 | Correction / relief zone displacement (plateau + smoothstep) | O(n) (or O(n_affected) with BVH range query) |
| ALG-47 | Zone overlap detection | O(z²·n) worst, O(z·n) with masks |
| ALG-48 | Global axis length adjustment (anisotropic scaling about the frame origin) | O(n) |
| ALG-49 | Circumference adjustment at a level with tapered band | O(n) |
| ALG-50 | Post-operation geometric guard | Incremental: O(k log m) for k affected faces [H] |
| ALG-52 | Export frame transform and manufacturing geometry hand-off | O(m) |
| ALG-53 | Op-log replay engine with content-addressed cache | Σ op costs; edit of op k recomputes ops k…n only |
| ALG-54 | Canonical geometry hash | O(n + m) |
| ALG-55 | Canonical JSON hash (RFC 8785 JCS) | O(size) |
| ALG-56 | Display LOD payload (jude-mesh/1) | O(m log m) |
| ALG-57 | Scalar field colour mapping | O(n) |
| ALG-58 | Audit hash chain | O(1) append; O(N) verify |
| ALG-59 | Method agreement analysis (Bland–Altman) | O(n) |
| ALG-60 | Off-screen rendering of the deviation image | O(m) per view |
| ALG-61 | Operation registry and parameter-schema validation | O(size of params) |

## 3. Memory model (derived arithmetic — to be verified by BM-06)

- Closed manifold triangle mesh: n ≈ m/2 vertices for m faces (Euler, genus 0).
- DS-01 in memory: 24 B·n + 12 B·m ≈ 24 B per face.
- Binary STL file: 84 + 50·m bytes. Import peak (file bytes + float64 soup 72 B/face + unique/sort workspace ≈ 2× soup) ≈ 250 B per face [derived, H].
- Phantom series used by BM-01 (exact counts):

| Subdivision s | Faces m = 20·4^s | Vertices n = 10·4^s + 2 | STL bytes 84 + 50m | Estimated import peak (250 B/face, H) |
|---|---|---|---|---|
| 4 | 5,120 | 2,562 | 256,084 | 1 MiB |
| 5 | 20,480 | 10,242 | 1,024,084 | 5 MiB |
| 6 | 81,920 | 40,962 | 4,096,084 | 20 MiB |
| 7 | 327,680 | 163,842 | 16,384,084 | 78 MiB |
| 8 | 1,310,720 | 655,362 | 65,536,084 | 312 MiB |

## 4. Benchmark methodology

| ID | Benchmark | Data | Measures | Analysis / decision | Constraint |
|---|---|---|---|---|---|
| BM-01 | Synthetic scaling series | Icosphere and ellipsoid phantoms at subdivisions 4…8 (face counts 20·4^s = 5 120; 20 480; 81 920; 327 680; 1 310 720) plus T3 defect variants (holes, ghost layer, flipped faces) | Each kernel op and integrity job: wall time (median, p95 over ≥ 20 runs after warm-up), peak RSS, output hash | Fit time ∝ m^α; compare with stated complexity; report hardware (CPU model, cores, RAM), image digest, library versions | Synthetic only — allowed before VER-22 |
| BM-02 | Real clinic scans | ≥ 3 anonymised clinic exports per format after VER-22 (BL-134) | File size, face count, components, hole sizes, ghost-layer counts, contour sizes at base plane, all PM timings | Descriptive statistics per scan; sets N, S, n_max, LOD budget proposals | Only after VER-22 and SEC-17 gate |
| BM-03 | Determinism | 10 reference designs (T9) | Distinct geometry hashes over 100 regenerations on host A, and on host B with same image | Pass = 1 hash per design per host; cross-host result recorded (RG-10) | Synthetic first |
| BM-04 | Viewer performance | LOD meshes at budgets 50k…1M faces on each supported browser and min-spec PC | Time to first render, fps while orbiting, BVH build time (worker), memory | Choose LOD budget = largest budget meeting fps target (TBD) | Needs NFR-01/02 |
| BM-05 | Platform latency | API + Postgres (Supabase) + Storage | Job claim latency, audit append overhead, blob put/get throughput, upload throughput from clinic network | p50/p95 under 1…5 concurrent scripted users | Needs OQ-FS-08 deployment |
| BM-06 | Memory profile | Worker jobs at N | Peak RSS per job type | Sets worker memory limit and pool size k | — |
| BM-07 | End-to-end job latency | Regenerate (per op type), review, export, report | Wall time p95 | Feeds PM-06…08 and NFR-04 | — |

Reporting rule: every benchmark result records host CPU model, cores, RAM, OS, container image digest, Python and library versions, input fixture hash, warm-up policy, number of runs, median and p95. Results are stored as files in the repository and are the only source for PM values.

## 5. Experiments that gate technology lock-in

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

## 6. Scalability

- Pilot load: one clinic, ≤ 5 concurrent users (A-16, to confirm). Horizontal scaling = more worker processes (pool size k from BM-06); API is stateless.
- Long operations are always jobs (202 + polling); UI never blocks on geometry.
- Interactive editing relies on per-op cache (ALG-53): an edit of op k recomputes only ops k…n; LOD regenerated per edit (PM-06, X-04).
- Storage growth per case = original scan + derived artifacts (scan_mm, scan_prepared, positives per version, LODs, fields, exports, reports); formula per artifact = jude-arr/1 header + 24 B·n + 12 B·m (+ 4 B·n per scalar field). Measure on BM-02 to size the Supabase plan and the separate backup target.
- Export and report generation scale linearly with faces (ALG-06, ALG-60).
