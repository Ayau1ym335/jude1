# syntax=docker/dockerfile:1
# XC-EXP-06 (X-06): numba determinism and warm-up. Python 3.12, linux/amd64 (IDR-09),
# versions as in the X-08 SOUP baseline. Built once in CI and loaded unchanged on the second
# host, so both hosts run the very same image (same image ID).
ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.10.6@sha256:2f2ccd27bbf953ec7a9e3153a4563705e41c852a5e1912b438fc44d88d6cb52c

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE}
COPY --from=uv /uv /bin/uv
COPY requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache --only-binary :all: --require-hashes -r /tmp/requirements.txt
# Determinism regime (TD-19): single-threaded; fastmath/parallel off in the kernel decorators.
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMBA_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY kernels.py probe.py /opt/x06/
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin x06
USER 10001
ENTRYPOINT ["python", "/opt/x06/probe.py"]
