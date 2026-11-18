# XC-EXP-08 — X-08 container image build matrix

| Field | Value |
|---|---|
| Task | XC-EXP-08 (X-08) — evidence for TQ-09 |
| Requirement | SEC-09 |
| Date | 2026-11-19 |
| Scope | Python 3.12 · linux/amd64 only (IDR-09 narrowed the original 3.12/3.13 × amd64/arm64 matrix) |
| Status | **Accepted** — recommendation §6 signed by the engineering lead on 2026-11-19 (§7) |

## 1. Question

Can the worker image hold every candidate wheel of LIBRARY_COMPARISON_v1.0 together, as binary wheels only, on Python 3.12 / linux/amd64, and run each library inside the production sandbox shape? The production shape is a read-only root filesystem, a non-root user and no network (IDR-07). What goes into the SOUP list?

## 2. Method

The harness is in `infra/experiments/x08/`:

- **`Dockerfile`:**
  - Base: `python:3.12.16-slim-bookworm` and `uv 0.10.6`, both pinned by digest.
  - System packages: the WeasyPrint stack (Pango, HarfBuzz subset) and `fonts-dejavu-core` for Cyrillic.
  - Wheels: `uv pip install --only-binary :all: --require-hashes` from a hash-locked `requirements.txt`, so there are no source builds.
  - Determinism environment: `OMP/OPENBLAS/MKL/NUMBA_NUM_THREADS=1`.
- **`probe.py smoke`:** runs in a fresh process with `--read-only --tmpfs /tmp --network none`, as user uid 10001. It times each import and makes one working call per library:
  - numpy: matmul;
  - scipy: `csgraph.connected_components`;
  - numba: `@njit(fastmath=False, parallel=False)` ordered sum, timing the first call (JIT) and the second;
  - fast-simplification: 50 % reduction of a 3 042-triangle grid;
  - WeasyPrint: renders Cyrillic HTML to a PDF.
- **`probe.py soup`:** lists every installed distribution with its licence, the Debian packages of the PDF stack, and the numpy BLAS configuration.
- **`run.sh`:** 3 builds with `--no-cache` (base image already pulled), then 20 probe runs. `summarize.py` computes the median and nearest-rank p95.

Every input is synthetic; no patient data is used.

**Candidate set (top level):** numpy 2.5.4, scipy 1.18.1, numba 0.68.1 (with llvmlite 0.50.0), fast-simplification 0.2.0, weasyprint 70.0. The resolved closure has 18 distributions; see `*/soup.csv`.

## 3. Hosts

| | Local | CI (`x08-image-matrix`, run 44397860807) |
|---|---|---|
| CPU | AMD Ryzen 5 7535HS | Intel Xeon Platinum 8573C |
| vCPU visible to Docker | 12 | 2 |
| Memory visible to Docker | 7.4 GiB | 7.7 GiB |
| Docker | Docker Desktop 29.9.2, WSL2 kernel 6.6.87.2 | Ubuntu 24.04.5 LTS (GitHub-hosted runner) |
| Image ID | `sha256:48709ad8a6f3…` | `sha256:357ccf5c457c…` |
| Image size reported | 855 MB (containerd store) | 617 MB (overlay2) |

The raw data is in `docs/experiments/XC-EXP-08/local/` and `…/ci/`: `builds.csv`, `smoke.jsonl`, `soup.json`, `soup.csv`, `env.json` and `summary.json`.

## 4. Results

**All 20 of 20 runs passed every check on both hosts** (`all_ok = true`). Every candidate installs from wheels; nothing builds from source.

| Measure (seconds) | Local median | Local p95 | CI median | CI p95 |
|---|---|---|---|---|
| Build, `--no-cache` (n = 3) | 151.8 | 183.4 | 16.8 | 18.7 |
| Container start → exit (whole probe) | 9.67 | 13.06 | 3.06 | 3.10 |
| import numpy | 0.359 | 0.513 | 0.155 | 0.157 |
| import scipy (csgraph) | 1.233 | 3.215 | 0.474 | 0.481 |
| import numba | 1.024 | 1.772 | 0.457 | 0.468 |
| import fast_simplification | 0.014 | 0.028 | 0.007 | 0.008 |
| import weasyprint | 2.132 | 3.934 | 0.920 | 0.929 |
| numba first call (JIT, trivial loop) | 0.856 | 2.474 | 0.408 | 0.415 |
| numba second call | 4e-6 | 6e-6 | 3e-6 | 3e-6 |
| fast-simplification, 3 042 → ~1 521 triangles | 0.0018 | 0.0026 | 0.0011 | 0.0012 |
| WeasyPrint, Cyrillic HTML → PDF | 0.121 | 0.179 | 0.059 | 0.062 |

The local host is slower and noisier because Docker Desktop runs in a WSL2 VM shared with the desktop. The CI figures are the cleaner baseline. The numba first-call time is for a trivial function. The warm-up of real kernels and their determinism are X-06 (XC-EXP-06).

## 5. Findings

1. **The candidate set is compatible.** numba 0.68.1 requires `numpy >=1.22,<2.6`; scipy 1.18.1 requires `numpy >=2.0,<2.8`. numpy 2.5.4 satisfies both.
2. **The SOUP list is identical on both hosts.** The resolved versions come from the hash lock, so the build host has no influence.
3. **Rebuilding does not reproduce the image bit for bit.** The image IDs differ between the two hosts for the same Dockerfile and lock: the Debian package layer (apt index, file timestamps) is not reproducible. This confirms IDR-19: approvals must reference a **retained** image digest, never "rebuild the same Dockerfile".
4. **OpenBLAS uses `DYNAMIC_ARCH`.** numpy and scipy bundle scipy-openblas 0.3.34, which picks its compute kernel by CPU at runtime. Hosts with different CPUs (here AMD Zen 3+ vs Intel Xeon) can run different BLAS code paths, which is a cross-host bit-equality risk for TD-19 and BM-03 wherever the kernel calls BLAS (matmul, `linalg`).
5. **fontconfig needs a writable cache.** Under the read-only root FS with a non-root user, fontconfig logged "No writable cache directories" until the image built the system font cache (`fc-cache -f`) and set `XDG_CACHE_HOME=/tmp/.cache` on the tmpfs. This is now in the Dockerfile.
6. **Licences to review:**
   - `pyphen` 0.18.1, a WeasyPrint dependency, is tri-licensed: GPL-2.0+ / LGPL-2.1+ / MPL-1.1. The project must elect LGPL or MPL in the SOUP record.
   - `llvmlite` is `BSD-2-Clause AND Apache-2.0 WITH LLVM-exception`.
   - The rest are permissive (BSD, MIT, Apache-2.0, MIT-CMU, MIT-0).
7. **`pip` 25.0.1 comes from the base image.** The worker does not need it at runtime.

## 6. Proposed recommendation

1. **Lock TQ-09:** Python 3.12.16, linux/amd64, with the five candidates at the versions above, wheels only, hash-locked. Record `soup.csv` as the SOUP baseline (SEC-09).
2. **Retain built images by digest** for the retention period, as IDR-19 requires. Do not treat a rebuild as equivalent (finding 3). Push the worker image to a registry and record its RepoDigest per design version.
3. **Pin the BLAS kernel path for determinism:** set `OPENBLAS_CORETYPE` to one fixed core type in the worker image, *or* keep BLAS calls out of hash-relevant kernel paths. Decide in X-06 / BM-03 on two hosts. Until then, kernel code should not rely on BLAS results for anything that is hashed.
4. **Carry over to the production worker image:** prebuilt font cache, `XDG_CACHE_HOME` on tmpfs, thread variables set to 1, `pip` removed from the runtime stage.
5. **Pin the Debian packages** through a dated `snapshot.debian.org` source, or record their versions per image (as `soup.csv` does now). Today they float with the bookworm archive.
6. **Licence:** record the `pyphen` election (LGPL-2.1+). Legal confirmation is outside engineering (LQ list, EXT task).

## 7. Sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| Engineering lead | Ayau | 2026-11-19 | ☑ Accept §6 ☐ Accept with changes ☐ Reject |

Form of approval: written statement in the implementation session on 2026-11-19, "отчёт X-08 (§7 в docs/experiments/XC-EXP-08.md) подписано". No changes to §6 were requested.

**Effect:** TQ-09 is closed with the set in §6.1. Items §6.2–§6.5 are carried into the production worker image when the worker task that first needs these libraries lands; §6.3 (BLAS kernel path) is decided in X-06 / BM-03. §6.6 (pyphen licence election) still needs legal confirmation outside engineering.

## 8. Reproduce

- **Local:** `bash infra/experiments/x08/run.sh <out_dir> 3 20` (needs Docker and python3).
- **CI:** run the workflow `x08-image-matrix` (dispatch, or any PR that touches `infra/experiments/x08/**`). Its artifact `x08-ci` holds the same files.
