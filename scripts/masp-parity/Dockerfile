# MASP parity harness: runs ro-crate-masp's JavaScript validator at a pinned
# commit and captures reference outputs for crategraph's Python parity test.
# Build and run through run.sh; see README.md.

FROM ghcr.io/astral-sh/uv:0.9.5@sha256:f459f6f73a8c4ef5d69f4e6fbbdb8af751d6fa40ec34b39a1ab469acd6e289b7 AS uv

FROM node:22-bookworm-slim@sha256:3ed98443660ff48413b5af19ecefce3b9d50845a901a43420d47cc63a9fddbe9

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv runs scripts/owl-to-masp.py for owl-to-masp.test.js.
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_CACHE_DIR=/opt/uv/cache \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python

ARG MASP_COMMIT=6d7a018baf827b5716d79a17462e3b3edb15725f
ENV MASP_DIR=/opt/ro-crate-masp \
    MASP_COMMIT=${MASP_COMMIT}

# The lockfile at this commit is slightly out of sync with package.json
# (npm ci reports missing chokidar 3 entries), so fall back to npm install,
# which keeps the locked versions (ro-crate 3.7.2) and adds what is missing.
RUN git clone https://github.com/Language-Research-Technology/ro-crate-masp.git "$MASP_DIR" \
    && cd "$MASP_DIR" \
    && git checkout "$MASP_COMMIT" \
    && (npm ci || npm install --no-audit --no-fund) \
    && uv run scripts/owl-to-masp.py --help > /dev/null \
    && chmod -R a+rwX /opt/uv

COPY capture-hook.js batch.js pairs.json /harness/

WORKDIR /opt/ro-crate-masp
ENV HOME=/tmp \
    MASP_PARITY_FIXTURES=/out/fixtures \
    MASP_PARITY_LOCAL=/out/local \
    CRATEGRAPH_DIR=/crategraph

# Failing JS tests are recorded in the case files and suite summary, not fatal.
CMD ["sh", "-c", "npx mocha --require /harness/capture-hook.js --timeout 120000 test/masp-validator*.test.js test/ldac-*.test.js test/ro-crate-2-validator.test.js test/workflow-validator.test.js test/owl-to-masp.test.js 2>&1 | tee /out/local/suite.log; node /harness/batch.js 2>&1 | tee /out/local/batch.log"]
