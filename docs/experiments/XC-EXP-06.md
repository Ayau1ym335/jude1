# XC-EXP-06 — X-06 numba determinism and JIT warm-up on two hosts

| Field | Value |
|---|---|
| Task | XC-EXP-06 (X-06) — evidence for TD-02 and TQ-11 |
| Requirement | VER-07 (determinism regime TD-19 / ADR-010) |
| Date | 2026-11-20 |
| Scope | Python 3.12 · linux/amd64 · numpy 2.5.4, numba 0.68.1, llvmlite 0.50.0 (X-08 SOUP versions) |
| Status | **Proposed.** The recommendation in §6 needs the engineering lead's signature (§7). |

## 1. Question

TD-02 adopts numba for the scalar inner loops (BVH, predicate filters, triangle tests) **if X-06 passes**. That needs two things:

1. **Determinism.** With fastmath off and parallel off, numba must give bit-identical outputs across fresh processes and across two different hosts running the same image.
2. **Warm-up.** The JIT warm-up cost at worker start must be acceptable.

## 2. Method

The harness is in `infra/experiments/x06/`.

- **Image (`Dockerfile`):**
  - Base: `python:3.12.16-slim-bookworm` and `uv 0.10.6`, both pinned by digest.
  - Wheels: hash-locked, binary only (`requirements.txt`).
  - Threads: `OMP/OPENBLAS/MKL/NUMBA_NUM_THREADS=1`.
  - Sandbox: user uid 10001; runs with a read-only root, `--network none` and `/tmp` as tmpfs.
- **Kernels (`kernels.py`):** seven stand-ins for the BM-01 kernels. They cover the places where floating-point non-determinism usually appears. Every kernel uses `@njit(fastmath=False, parallel=False, cache=True, error_model="numpy")`.

  | Kernel | Why it is included |
  |---|---|
  | `ordered_sum` | Long sequential reduction (200 000 values) |
  | `orient3d_float` | Float orient3d determinant (the filter in front of the exact predicates, ALG-11). Sensitive to FMA contraction. |
  | `closest_point_triangle` | Branchy point–triangle test with divisions (ALG-33/40) |
  | `transcendental` | libm `sin`, `cos`, `exp`, `log1p`, `atan2`, `sqrt` |
  | `laplacian_smooth` | Neighbour accumulation over a CSR list, 10 Jacobi iterations |
  | `median_split_order` | BVH build ordering: widest axis, stable merge sort |
  | `hermite_profile` | ALG-63 monotone cubic Hermite (Fritsch–Carlson) |

- **Inputs:** synthetic only, generated from a fixed PCG64 seed, so they are bit-identical on every host. No patient data is used.
- **`probe.py run`:** one fresh Python process. It imports, calls each kernel twice (the first call includes JIT compilation) and records the SHA-256 of the raw output bytes. There is no rounding or normalisation, so any bit difference counts.
- **Series:** 100 fresh processes per series. CPU target ∈ {`host` (numba compiles for the detected CPU), `generic` (`NUMBA_CPU_NAME=generic`)} × cache ∈ {`cold` (empty cache directory for each process), `warm` (one shared cache directory; run 1 fills it and is left out of the timings)}. 4 series × 100 = **400 processes per host**.
- **Same image on both hosts:** CI built the image once and saved it as an artifact (`docker save`); the local host loaded that artifact (`docker load`). The layer digests are identical (`XC-EXP-06/image_identity.json`). The two image IDs differ only because Docker Desktop's containerd store reports the digest of the image index, while the CI runner reports the config digest `sha256:96f3a1525ef8…`.

## 3. Hosts

| | CI (`x06-numba-determinism`, run 44532823988) | Local workstation |
|---|---|---|
| CPU | Intel Xeon 6975P-C | AMD Ryzen 5 7535HS |
| LLVM host CPU | `graniterapids` (AVX-512) | `znver3` (AVX2, no AVX-512) |
| vCPU / memory visible to Docker | 4 / 15.3 GiB | 12 / 7.4 GiB |
| Docker | Ubuntu 24.04.5 LTS, kernel 7.0.0-1014-aws | Docker Desktop 29.9.2, WSL2 kernel 6.6.87.2 |
| Runner | `run.sh` | `run_detached.sh` (same series in one detached container, so the run survives the terminal session) |

**About the local timings:** other projects' containers ran on the workstation at the same time, and one of them was in a restart loop. The local timings are therefore inflated and noisy. The warm-up figures for the decision come from CI; the local figures are for reference only. Determinism does not depend on load.

The raw data is in `docs/experiments/XC-EXP-06/ci/` and `…/local/`: `series-*.jsonl`, `results.csv` (one row per run × kernel), `summary.json` and `env.json`. The cross-host comparison is in `cross_host.json`.

## 4. Results

### 4.1 Determinism: passes

| Check | CI | Local |
|---|---|---|
| Distinct output hashes per kernel within each series (100 processes) | 1 for all 7 kernels × 4 series | 1 for all 7 kernels × 4 series |
| First call = second call in the same process | 2 800 / 2 800 | 2 800 / 2 800 |
| Same hash as the other host | 28 / 28 (7 kernels × 4 series) | 28 / 28 |
| `host` code = `generic` code on the same host | 7 / 7 | 7 / 7 |
| Cache-loaded code (`warm`) = freshly compiled code (`cold`) | 7 / 7 | 7 / 7 |

Output hashes, identical on every run of both hosts (first 16 hex digits):

| Kernel | SHA-256 |
|---|---|
| `ordered_sum` | `1c8beedff50769c7…` |
| `orient3d_float` | `51b960b32668944a…` |
| `closest_point_triangle` | `a6bc036aaa5d0cf8…` |
| `transcendental` | `8f83c31d14fd7f0d…` |
| `laplacian_smooth` | `aa18ffff658e68fd…` |
| `median_split_order` | `3833274b7a9ee757…` |
| `hermite_profile` | `067bb56ae43d26e8…` |

AVX-512 code on Intel and AVX2 code on AMD gave the same bits. So with fastmath off, LLVM did not contract the multiply-adds into FMA or reorder the reductions, and libm gave the same results on both hosts.

### 4.2 Warm-up (seconds)

| Measure (all 7 kernels) | CI median | CI p95 | Local median | Local p95 |
|---|---|---|---|---|
| `import numba` + kernels module | 0.757 | 0.766 | 1.688 | 1.978 |
| First calls, `host`, cold (JIT compile) | 5.034 | 5.116 | 12.536 | 14.283 |
| **Total warm-up, `host`, cold** | **5.791** | **5.881** | 14.299 | 16.183 |
| Total warm-up, `generic`, cold | 5.387 | 5.494 | 14.279 | 17.852 |
| **Total warm-up, `host`, warm (cache hit)** | **1.136** | **1.153** | 2.505 | 2.692 |
| Total warm-up, `generic`, warm | 1.128 | 1.142 | 2.722 | 2.889 |
| Steady state, second call of all 7 kernels | 0.021 | 0.021 | 0.038 | 0.049 |

With n = 100 for cold series and n = 99 for warm series, p95 is nearest-rank.

JIT time per kernel (CI, `host`, cold, median): `closest_point_triangle` 2.01 s, `median_split_order` 1.80 s, `ordered_sum` 0.46 s, `hermite_profile` 0.31 s, `laplacian_smooth` 0.24 s, `orient3d_float` 0.13 s, `transcendental` 0.09 s. Compilation time grows with the size of the code and with array slicing, not with the input data.

The cache cuts warm-up by about 5× (5.8 s → 1.1 s). Most of what is left is the import.

## 5. Limits of this evidence

- **The kernels are stand-ins.** The real BVH, predicate and triangle kernels arrive with their TT-K tasks in M1. Each one must keep its own golden hash in the CI `determinism` stage, and BM-01 must be re-run on them. This experiment shows the regime works; it does not certify future kernels.
- **Two x86-64 hosts.** They differ in vendor and vector width (AVX-512 versus AVX2). arm64 is out of scope (IDR-09).
- **Seven kernels compile in about 5 s.** Total warm-up for the full M1 kernel set will scale with the amount of code. It has to be measured again in BM-01.
- **No warm-up budget exists yet.** TD-02 says "warm-up acceptable" and PERFORMANCE_REQUIREMENTS leaves the budget TBD until BM-01. This report gives the numbers; it does not set a threshold.

## 6. Recommendation (needs the engineering lead's signature)

1. **Close TQ-11 and TD-02 with option (b):** numpy plus numba for the scalar inner loops. The determinism condition of X-06 is met on two hosts with the same image. The C++ extension (option c) is not needed for determinism.
2. **Required decorator settings:** `fastmath=False`, `parallel=False`, `error_model="numpy"`, plus `NUMBA_NUM_THREADS=1` in the image. These match TD-19. The kernel lint should enforce the decorator settings when the first numba kernel lands (XC-SHR-01 is the first candidate).
3. **Compile with `NUMBA_CPU_NAME=generic`, and fill the numba cache at image build time.** `generic` gave the same bits and costs no measurable steady-state speed on these kernels (0.021 s for both). Because its code does not depend on the CPU, the cache that the image build fills is valid on any amd64 host. A worker then starts with a cache hit (about 1.1 s on CI) instead of a full JIT (about 5.8 s). The cache directory must be inside the image, because the production root filesystem is read-only.
4. **The worker warms up before it reports ready.** It calls each registered kernel once on a tiny synthetic input before `/healthz` returns 200, so the first user job never pays the JIT cost (TD-02 constraint).
5. **Keep the cross-host check permanent.** Run the `x06-numba-determinism` workflow, or its successor in the `determinism` stage, on every change to the kernel image. Record the image digest per design version (TD-19).

## 7. Sign-off

| Role | Decision | Date | Notes |
|---|---|---|---|
| Engineering lead | _pending_ | | |
