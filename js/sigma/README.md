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

After bumping dependency versions in `package.json`.
