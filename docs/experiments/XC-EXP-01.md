# XC-EXP-01 — X-01 determinism and tie handling of candidate libraries

| Field | Value |
|---|---|
| Task | XC-EXP-01 (X-01): evidence for TD-03, TD-11, TQ-05 and TQ-07 |
| Requirements | VER-07 (determinism, TD-19 / ADR-010), NFR-03 |
| Date | 2026-11-28 |
| Scope | Python 3.12 · linux/amd64 · closest point: own BVH (XC-SHR-02) vs libigl vs Open3D · display LOD: fast-simplification vs meshoptimizer · smoothing: own windowed-sinc only (VTK excluded by IDR-11) |
| Status | **Proposed.** Recommendation §6 waits for the engineering lead's signature (§7). |

## 1. Question

1. **TQ-05 (closest point, ray cast).** Should the kernel use libigl, Open3D or its own numba BVH? The criteria are determinism, tie handling, licence and SOUP size.
2. **TQ-07 (display LOD).** Should LOD decimation use fast-simplification or meshoptimizer?
   - The LOD is display only (INV-10), so it is never a kernel input.
   - Determinism still helps caching of the LOD payload.

The protocol is in TECHNICAL_OPEN_QUESTIONS §3 and PERFORMANCE_REQUIREMENTS §4: 100 runs on each of 2 hosts, on BM-01 phantoms and on tie fixtures with equidistant faces.

**Smoothing is out of scope.** IDR-11 excludes VTK, so TQ-06 has only one candidate: the own windowed-sinc. That implementation arrives with FN-KOP-12 (M4), and its determinism will be covered by the CI `determinism` stage then.

## 2. Method

The harness is in `infra/experiments/x01/`.

- **Image (`Dockerfile`):**
  - Base: `python:3.12.16-slim-bookworm` and `uv 0.10.6`, both pinned by digest.
  - Candidate wheels: hash-locked and binary only (`requirements.txt`).
  - meshoptimizer: built from its hash-pinned source release in a separate build stage, because it publishes no wheels (finding 5).
  - The shipped kernel source (`jude_kernel`), unchanged.
  - Fixtures: the T1 phantoms and the T14 tie fixture.
- **Determinism regime:** TD-19 and X-06 §6:
  - `*_NUM_THREADS=1`;
  - `NUMBA_CPU_NAME=generic`;
  - the numba cache is filled at image build time.
- **Sandbox:** user uid 10001, a read-only root filesystem, `--network none` and `/tmp` on a tmpfs.
- **Inputs:** synthetic only.
  - **Phantoms** (BM-01 series, T1): `icosphere_s4_r75` (5 120 faces), `icosphere_s6_r75` (81 920), `ellipsoid_asym_s6` (81 920) and `torus_R60_r20` (9 216).
  - **Queries per phantom:**
    - every vertex. Each vertex query is an exact tie between all its incident faces at distance 0, so the phantoms contain tens of thousands of real ties;
    - 20 000 points at 0.3–1.5 × the bounding radius, drawn from PCG64 with a fixed seed, so they are bit-identical on every host.
  - **Tie fixture (T14):** `cube_40` with 8 queries whose tied face sets and "smallest face_id" answers were computed exactly.
- **`probe.py run`** is one fresh process:
  - every library processes every phantom twice in the same process;
  - the probe records the SHA-256 of each raw output array (closest-point face, squared distance, point; LOD V and F), with no rounding, so any bit difference counts;
  - it also records the time of the first and of the second call.
- **`probe.py agree`** compares libigl and Open3D with the own BVH (face choice, squared distance, distance in mm) and records the face each library picks at the T14 tie queries.
- **Series:** 100 fresh processes per host. `summarize.py` counts the distinct hashes over the runs and computes the median and nearest-rank p95. `compare.py` compares the two hosts.
- **Same image on both hosts.**
  - CI built the image once and saved it, in 50 MB parts with SHA256SUMS. The local host loaded those parts.
  - All 16 layer diff IDs are identical (`XC-EXP-01/image_identity.json`). The config digest in the saved image is the CI image ID `sha256:2b5cc866dd22…`.
  - Docker Desktop reports the digest of the image index instead (`sha256:1aa37b5a22d9…`), as it did in X-06.

**Candidate versions:**

| Library | Version | Licence | Python distributions added to the kernel's 9 |
|---|---|---|---|
| numpy / numba / jsonschema (kernel) | 2.5.4 / 0.68.1 / 4.26.0 | BSD / BSD / MIT | (the base set: 9) |
| libigl | 2.6.3 | MPL-2.0 | +2 (scipy and what it pulls in) |
| Open3D, CPU build | 0.20.0 | MIT | **+53** (dash, flask, plotly, ipython, ipywidgets, nbformat, pydantic, requests…); installs 308 MB |
| fast-simplification | 0.2.0 | MIT | +1 |
| meshoptimizer | 0.2.30a0 (alpha) | MIT | 0, but there is no wheel: built from source |

## 3. Hosts

| | CI (`x01-library-determinism`, run 46115881471) | Local workstation |
|---|---|---|
| CPU | Intel Xeon 6975P-C | AMD Ryzen 5 7535HS |
| vCPU / memory visible to Docker | 4 / 15.3 GiB | 12 / 7.4 GiB |
| Docker | Ubuntu 24.04.5 LTS, kernel 7.0.0-1018-aws | Docker Desktop, WSL2 |
| Instruction set | AVX-512 | AVX2 (no AVX-512) |

The raw data is in `docs/experiments/XC-EXP-01/ci/` and `…/local/`: `series.jsonl` (one line per process), `agree.json`, `summary.json` and `env.json`. The cross-host comparison is in `cross_host.json`.

**About the local timings:** the workstation also ran the project's development stack during the series, so its timings are for reference. The decision figures come from CI. Determinism does not depend on load.

## 4. Results

### 4.1 Determinism

| Check | CI | Local |
|---|---|---|
| Runs without error | 100 / 100 | 100 / 100 |
| Distinct hashes per output over 100 processes (12 closest-point groups × 3 arrays, 8 LOD groups × 2 arrays) | 1 for all 52 | 1 for all 52 |
| First call = second call in the same process | 2 000 / 2 000 | 2 000 / 2 000 |
| Same hashes as the other host (`cross_host.json`) | 20 / 20 groups | 20 / 20 groups |
| `agree.json` (agreement and tie picks) identical on both hosts | yes | yes |

Process time on the local host was 14.8 s (median) and 23.0 s (p95), of which import and warm-up took 4.7 s (median); see §3 on load.

All three closest-point libraries and both decimators are deterministic: one hash per output on each host, the same result for the first and second call in each process, and the same hashes on both hosts.

### 4.2 Agreement with the own BVH (CI host; identical on the local host)

| Library / phantom | Queries | Different face chosen | … of which at exactly the same distance (tie) | Squared distance bit-equal | Max distance difference (mm) |
|---|---|---|---|---|---|
| libigl / icosphere_s4 | 22 562 | 3 673 | 3 137 | 10 719 | 2.8e-14 |
| libigl / icosphere_s6 | 60 962 | 35 624 | 35 079 | 49 070 | 2.8e-14 |
| libigl / ellipsoid_asym_s6 | 60 962 | 36 952 | 36 099 | 49 906 | 2.8e-14 |
| libigl / torus | 24 608 | 9 513 | 8 388 | 16 719 | 2.8e-14 |
| Open3D / icosphere_s4 | 22 562 | 2 437 | 1 704 | 2 932 | 7.4e-6 |
| Open3D / icosphere_s6 | 60 962 | 27 497 | 26 568 | 41 377 | 8.2e-6 |
| Open3D / ellipsoid_asym_s6 | 60 962 | 28 360 | 26 910 | 41 894 | 7.4e-6 |
| Open3D / torus | 24 608 | 6 986 | 3 312 | 5 327 | 1.1e-5 |

- **libigl** computes the same distances to within about 1 ulp, but not bit for bit: 18–52 % of squared distances differ in the last bits. At ties it chooses a different face from the own BVH in most cases.
- **Open3D** works in float32 (vertices, queries and results). Its distances differ by up to 1.1e-5 mm. That is far inside DEC-025's e = 0.011 mm, but it is not the float64 geometry the kernel hashes.

### 4.3 Tie handling (T14 `cube_40`, 8 queries with exact tie sets)

| Library | Matches the "smallest face_id" rule | Picks outside the rule |
|---|---|---|
| Own BVH | 8 / 8 | — |
| Open3D | 8 / 8 | — (but 26 568 tie queries on icosphere_s6 differ from the own BVH: §4.2) |
| libigl | 5 / 8 | `centre_all_faces` → face 1 (rule: 0); `corner_region_40_40_40` → face 7 (rule: 2); `inside_near_two_walls` → face 10 (rule: 5) |

Every pick is inside the exact tie set: no library returns a wrong face. Neither libigl nor Open3D documents a tie rule. Their picks follow their own tree traversal order. Open3D matches the rule on T14 only because the cube's coordinates are small integers, which are exact in float32; on the phantoms its choices differ.

### 4.4 Timing (CI host, seconds; median / p95 over 100 processes)

| Closest point (build + all queries) | icosphere_s4 (22 562 q) | torus (24 608 q) | icosphere_s6 (60 962 q) | ellipsoid_asym_s6 (60 962 q) |
|---|---|---|---|---|
| Own BVH (numba) | 0.253 / 0.271 | 0.198 / 0.209 | 1.176 / 1.261 | 0.904 / 0.980 |
| libigl | 0.054 / 0.055 | 0.046 / 0.048 | 0.588 / 0.603 | 0.462 / 0.473 |
| Open3D (float32) | 0.048 / 0.049 | 0.030 / 0.030 | 0.263 / 0.269 | 0.212 / 0.220 |

| Display LOD (to 25 % of the faces) | icosphere_s4 | torus | icosphere_s6 | ellipsoid_asym_s6 |
|---|---|---|---|---|
| fast-simplification | 0.0020 / 0.0020 | 0.0034 / 0.0035 | 0.0369 / 0.0374 | 0.0418 / 0.0423 |
| meshoptimizer | 0.0008 / 0.0008 | 0.0015 / 0.0015 | 0.0200 / 0.0204 | 0.0189 / 0.0192 |

The table shows the second call. The first call is within a few per cent of it, except for fast-simplification, whose first call is 25–35 % slower. One whole process took 11.5 s (median) and 11.6 s (p95). Of that, import and kernel warm-up took 2.5 s, from the build-time numba cache.

## 5. Findings

1. **Every candidate is deterministic in this regime:** same image, single thread, fixed inputs. Determinism therefore does not separate the libraries. Bit-agreement with the kernel and tie handling do.
2. **Only the own BVH gives the kernel's answer bit for bit and follows the documented tie rule.**
   - libigl's distances differ in the last bits in up to 52 % of queries, and it breaks ties differently (3 of the 8 T14 queries).
   - Open3D is float32 throughout.
   - With either library, anchors (ALG-33), signed distance (ALG-40) and any other closest-point result that enters a hash would depend on the library's traversal order instead of the documented rule (T14, VER-07).
3. **The own BVH is 2–5× slower than libigl and 4–5× slower than Open3D** on these sizes. That is about 1.2 s for 61 000 queries on an 82 000-face mesh. No closest-point budget is set yet: PM rows are TBD until BM-01. Closest-point calls in the kernel are per edit (anchors) or per review (deviation map), so this cost is not per frame.
4. **Open3D is a heavy SOUP item:**
   - it adds 53 Python distributions (a web dashboard stack, Jupyter widgets, an HTTP client) and 308 MB;
   - even for geometry-only use it needs system libraries: `libEGL`, `libGL`, `libusb-1.0` (RealSense) and `libgomp`;
   - its optional ML modules link against libraries that are not installed (torch, TensorFlow, TBB).
5. **meshoptimizer's Python package is not eligible under the X-08 rule:**
   - It publishes only alpha source releases (0.2.30a0) and no wheels. Building it needs a C++ compiler and unpinned build requirements from PyPI.
   - It is faster than fast-simplification (about 2×) and reached the same face counts. The C++ library itself is mature; the Python binding is the problem.
6. **fast-simplification is deterministic across hosts** and adds one MIT distribution. It needs writable C-contiguous arrays (the kernel's read-only arrays must be copied), which is a detail for the FN-KOP-04 wrapper.
7. **numba will not load a pre-filled cache from a read-only directory.** It refuses to cache ("no locator available") unless `NUMBA_CACHE_DIR` is writable. With the production read-only root filesystem, the X-06 §6.3 build-time cache must be copied to the tmpfs at worker start, as the probe does, or placed on a writable volume. This applies to the worker image (XC-WSK-01 / the worker task that ships the cache).

## 6. Proposed recommendation

1. **Close TQ-05 with the own numba BVH** (XC-SHR-02) for every hashed or recorded spatial query: closest point, ray cast and broad phase.
   - libigl stays a CI oracle only (CLAUDE.md), compared within ulp-level agreement.
   - Open3D is not adopted. Its float32 precision, its undocumented tie choice and its SOUP footprint (finding 4) each rule it out.
2. **Close TQ-07 with fast-simplification 0.2.0** for the display LOD (FN-KOP-04), with copied writable inputs.
   - meshoptimizer is not adopted while it has no wheels (finding 5).
   - Revisit it if a wheel release appears and the LOD time becomes a bottleneck: it is about 2× faster.
3. **TD-03 / TD-11:** record the own BVH as the single spatial index and fast-simplification as the LOD library in the SOUP list, as planned for XC-EXP-LOCK.
4. **Performance follow-up, not a blocker:** BM-01 measures the own BVH at s7 and s8 with real kernel call patterns. If a budget is set and missed, optimise the numba traversal (for example a stack-based query batch) before reconsidering a library.
5. **Worker image:** copy the build-time numba cache to the tmpfs before warm-up, or mount a writable cache volume (finding 7).
6. **TQ-06 (smoothing):** no comparison is possible. The own windowed-sinc is the only candidate (IDR-11). Its determinism check joins the CI `determinism` stage with FN-KOP-12.

## 7. Sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| Engineering lead | | | ☐ Accept §6 ☐ Accept with changes ☐ Reject |

## 8. Reproduce

- **CI:** run the workflow `x01-library-determinism`, by dispatch or with any PR that touches `infra/experiments/x01/**`. It generates the large phantoms first (`jude-fixtures build` and `check`). Its artifact `x01-ci` holds the same files as `ci/`, and `x01-image` holds the image in parts.
- **Local, on the CI image:**
  1. Run `sha256sum -c SHA256SUMS`, then `cat x01-image.tar.gz.part-* | gunzip -c | docker load`.
  2. Run `bash infra/experiments/x01/run.sh jude-x01:exp <out_dir> 100`.
- **Compare hosts:** `python infra/experiments/x01/compare.py <ci_dir> <local_dir>`.
