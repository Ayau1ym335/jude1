# syntax=docker/dockerfile:1
# XC-EXP-08 (X-08, TQ-09): worker image with every candidate wheel, Python 3.12, linux/amd64
# (IDR-09). Experiment image only: the production worker image stays infra/docker/python.Dockerfile
# until the engineering lead accepts the recommendation in docs/experiments/XC-EXP-08.md.
ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.10.6@sha256:2f2ccd27bbf953ec7a9e3153a4563705e41c852a5e1912b438fc44d88d6cb52c

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE}
# WeasyPrint system libraries (Pango/HarfBuzz) + a Cyrillic-capable font for Russian reports.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/* \
 && fc-cache -f
# Font cache is built above; the runtime user writes its own cache to tmpfs /tmp
# (read-only root FS, IDR-07). Without this fontconfig logs "No writable cache directories".
ENV XDG_CACHE_HOME=/tmp/.cache
COPY --from=uv /uv /bin/uv
COPY requirements.txt /tmp/requirements.txt
# Wheels only (no source builds), hash-checked against the compiled lock.
RUN uv pip install --system --no-cache --only-binary :all: --require-hashes -r /tmp/requirements.txt
# Determinism regime (TD-19, ADR-010): single-threaded numerics, numba fastmath off by code.
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMBA_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY probe.py /opt/x08/probe.py
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin x08
USER 10001
ENTRYPOINT ["python", "/opt/x08/probe.py"]
