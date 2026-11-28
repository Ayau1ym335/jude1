# syntax=docker/dockerfile:1
# XC-EXP-01 (X-01): determinism and tie handling of candidate libraries.
# Closest point: own BVH (XC-SHR-02) vs libigl vs Open3D; display LOD: fast-simplification vs
# meshoptimizer. Python 3.12, linux/amd64 (IDR-09). Build from the repository root:
#   docker build --platform linux/amd64 -f infra/experiments/x01/Dockerfile -t jude-x01:exp .
# Built once in CI and loaded unchanged on the second host (same image on both hosts).
ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.10.6@sha256:2f2ccd27bbf953ec7a9e3153a4563705e41c852a5e1912b438fc44d88d6cb52c

FROM ${UV_IMAGE} AS uv

# meshoptimizer has no wheels (alpha source releases only). Experiment-only build from the
# hash-pinned sdist; its build requirements come unpinned from PyPI (recorded as a finding).
FROM ${PYTHON_IMAGE} AS meshopt
RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*
COPY infra/experiments/x01/meshopt.txt /tmp/meshopt.txt
RUN pip download --no-deps --no-binary meshoptimizer --require-hashes -r /tmp/meshopt.txt -d /tmp/sdist \
 && pip wheel --no-deps -w /tmp/wheels /tmp/sdist/meshoptimizer-*.tar.gz

FROM ${PYTHON_IMAGE}
COPY --from=uv /uv /bin/uv
# Open3D imports its rendering stack even for geometry-only use: it needs libgomp (OpenMP),
# libEGL, libGL and libusb (RealSense support) at import time (a SOUP finding of X-01).
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libegl1 libgl1 libusb-1.0-0 && rm -rf /var/lib/apt/lists/*
COPY infra/experiments/x01/requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache --only-binary :all: --require-hashes -r /tmp/requirements.txt
COPY --from=meshopt /tmp/wheels /tmp/wheels
RUN uv pip install --system --no-cache --no-deps /tmp/wheels/*.whl && rm -rf /tmp/wheels
# The shipped kernel, unchanged, and the synthetic fixtures (T1 phantoms, T14 ties).
COPY packages/kernel/src/jude_kernel /opt/x01/jude_kernel
COPY tests/fixtures/T1 /opt/x01/fixtures/T1
COPY tests/fixtures/T14 /opt/x01/fixtures/T14
# Determinism regime (TD-19) and the X-06 §6.3 cache: generic CPU target, cache filled at build
# time in /opt/x01/numba-cache. numba will not use a cache directory it cannot write to, and the
# root filesystem is read-only, so the probe copies it to the /tmp tmpfs at start (finding).
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMBA_NUM_THREADS=1 \
    NUMBA_CPU_NAME=generic \
    NUMBA_CACHE_DIR=/tmp/numba-cache \
    PYTHONPATH=/opt/x01 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN NUMBA_CACHE_DIR=/opt/x01/numba-cache python -c \
    "from jude_kernel.shared.warmup import warm_up; print(warm_up())"
COPY infra/experiments/x01/probe.py /opt/x01/probe.py
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin x01
USER 10001
ENTRYPOINT ["python", "/opt/x01/probe.py"]
