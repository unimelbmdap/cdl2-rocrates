# Sigma.js Bundle for crategraph

JS source for the vendored sigma.js + ForceAtlas2 bundle.

## Current versions

- graphology: 0.25.4
- sigma: 2.4.0
- graphology-layout-forceatlas2: 0.10.1

## Rebuild

    cd js/sigma
    npm install
    npm run build
    cp dist/sigma-fa2.min.js ../../crategraph/renderers/templates/vendor/

## When to rebuild

- After editing `src/main.js` (or any other source file bundled into `sigma-fa2.min.js`).
- After bumping dependency versions in `package.json`.

The Python test suite has a `TestBundleFreshness` check that catches
the common case of a stale bundle, but only for the currently-expected
API shape — editing `src/main.js` without rebuilding will fail that test.
