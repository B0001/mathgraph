# syntax=docker/dockerfile:1
#
# Batch image for mathgraph. Runs as Kubernetes Jobs, not a service: `setup`
# populates the corpus PVC once, then `bench`/`query`/`graph` read it.
#
#   docker build -t mathgraph:0.1.0 .
#   docker run --rm -v "$PWD/mathgraph-data:/data" mathgraph:0.1.0 bench
#
# The corpus is NOT baked into the image. `mathgraph setup` git-clones mathlib4
# plus six blueprint repos (~8GB); that belongs on a volume, not in a layer.

# --- Stage 1: build the environment ---
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.6.9 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.12

WORKDIR /app

# Dependency layer first so editing the package does not invalidate the solve.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Then the source and the project itself. README.md is required, not
# decorative: pyproject sets `readme = "README.md"` and hatchling fails the
# wheel build without it.
COPY mathgraph/ ./mathgraph/
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# --- Stage 2: runtime ---
FROM python:3.12-slim-bookworm AS runtime

# git is a hard runtime dependency, not a build tool: `mathgraph setup` shells
# out to `git clone --depth 1` for mathlib4 and each blueprint repo
# (mathgraph/setup_cmd.py). ca-certificates is what makes those HTTPS clones
# verify instead of failing.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/mathgraph/ ./mathgraph/
COPY pyproject.toml README.md ./

# COPY preserves host file modes, and this repo's sources are 0600 on disk.
# uv installs the project editable, so the venv's .pth points back at
# /app/mathgraph and the interpreter reads those files directly -- as uid 10001
# that fails with PermissionError before the CLI starts. a+rX (capital X) adds
# execute only to directories and already-executable files, which keeps the
# venv's bin/ scripts working.
RUN chmod -R a+rX /app/mathgraph /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Every command defaults --data-dir to $MATHGRAPH_DATA (mathgraph/cli.py:21).
# Pointing it at the mount means the Jobs need no --data-dir flag at all.
ENV MATHGRAPH_DATA=/data

# Retrieval and verification are numpy-bound and single-process; unpinned BLAS
# would fan out to every core on the node and thrash against the CPU limit.
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

# git refuses to operate without a writable HOME for its config; the root
# filesystem is read-only at runtime, so point it at the /tmp emptyDir.
ENV HOME=/tmp

# Non-root. Kubernetes pins runAsUser/fsGroup to this same 10001 so the corpus
# PVC is writable; keep the two in sync.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

RUN mkdir -p /data && chown 10001:10001 /data

USER 10001:10001

ENTRYPOINT ["mathgraph"]
CMD ["--help"]
