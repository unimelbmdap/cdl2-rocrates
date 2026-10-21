# Notice: ro-crate-masp material

The files in this directory are derived from
[ro-crate-masp](https://github.com/Language-Research-Technology/ro-crate-masp)
at commit `6d7a018baf827b5716d79a17462e3b3edb15725f`. That project is
licensed under the Apache License 2.0; a copy is in `LICENSE`.

## What was copied or derived

- `upstream/<name>/ro-crate-metadata.json`: verbatim copies of
  `profiles/<name>/profile-crate/ro-crate-metadata.json` for the profiles
  `ro-crate`, `ro-crate-2`, `ro-crate-masp`, `ldac`, `ldac-dmlex`, `workflow`
  and `software`. The `schema-org` profile (1.7 MB) was not copied.
- `profiles/<hash>.json`: profile crate snapshots taken while ro-crate-masp's
  test suite and the batch run executed. They are the upstream profiles above,
  some modified by the upstream tests, and the schema crates its
  `owl-to-masp.test.js` generates.
- `cases/*.json`: outputs of the ro-crate-masp JavaScript validator, with
  the target crates it validated:
  - crates built by the upstream test suite, including
    `test_data/sample-ro-crate-metadata.json`
  - the upstream examples `profiles/workflow/examples/minimal-example` and
    `profiles/ldac-dmlex/examples/abandon`
  - crategraph's own `docs/tutorials/data/paradisec/NT1`, referenced by path
    rather than copied

These files were produced by `scripts/masp-parity/` (see its README).

## Local only, not committed

The harness writes these cases to the gitignored `data/masp-parity/cases/`.
Their source crates are real collection metadata with no verified
redistribution licence:

- PARADISEC collections NT1 and NT3 from ro-crate-masp's
  `test_data/ldac/validator_tests/paradisec/collection/`, both as batch cases
  and as the `ldac-validator.test.js` PARADISEC suite cases
- the `test_data/ldac_examples/` corpora: `cooee`, `f2f` and `sydney_speaks`

Parity tests that need them skip when they are absent.
