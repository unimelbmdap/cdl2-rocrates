# MASP parity harness

Captures reference outputs from the JavaScript MASP validator in
[ro-crate-masp](https://github.com/Language-Research-Technology/ro-crate-masp)
so that crategraph's Python port can be checked against it
(`tests/validators/`). Regenerating the corpus is a manual step; CI only reads
the committed fixtures.

```bash
scripts/masp-parity/run.sh
```

This needs Docker with network access. Nothing JavaScript is installed in the
crategraph working tree: the image clones ro-crate-masp and installs its
dependencies inside the container, and outputs are written to mounted
directories.

## What runs

The image (`Dockerfile`) is pinned to:

| Component | Pin |
| --- | --- |
| Base image | `node:22-bookworm-slim@sha256:3ed98443660ff48413b5af19ecefce3b9d50845a901a43420d47cc63a9fddbe9` (Node v22.23.3) |
| uv (for `owl-to-masp.test.js`) | `ghcr.io/astral-sh/uv:0.9.5@sha256:f459f6f73a8c4ef5d69f4e6fbbdb8af751d6fa40ec34b39a1ab469acd6e289b7` |
| ro-crate-masp | commit `6d7a018baf827b5716d79a17462e3b3edb15725f` |
| ro-crate (npm) | 3.7.2, from the upstream lockfile; recorded in every case as `js_version` |

At this commit the upstream `package-lock.json` is slightly out of sync with
`package.json`, so `npm ci` fails and the build falls back to `npm install`,
which keeps the locked versions.

The container then runs two steps.

1. **Suite capture.** The ro-crate-masp mocha suite runs with
   `--require capture-hook.js` over these files:
   `test/masp-validator*.test.js`, `test/ldac-*.test.js`,
   `test/ro-crate-2-validator.test.js`, `test/workflow-validator.test.js` and
   `test/owl-to-masp.test.js`. Every `validateCrate` call becomes a case.
   Failing JS tests are recorded (`js_test.state` and `suite-summary.json`),
   not fatal.
2. **Batch run.** `batch.js` validates each pair in `pairs.json` from the raw
   files on disk: PARADISEC NT1 and NT3 against `ldac`; crategraph's own
   `docs/tutorials/data/paradisec/NT1` against `ldac` (mounted read-only); the
   `workflow` and `ldac-dmlex` example crates against their profiles; each
   `test_data/ldac_examples/*` crate against `ldac`; and the `ro-crate`,
   `ro-crate-2`, `ro-crate-masp`, `ldac`, `workflow` and `software` profiles
   against themselves. It also refreshes `tests/fixtures/masp/upstream/` and
   `tests/fixtures/masp/LICENSE` from the pinned clone.

## How capture works

`capture-hook.js` patches ro-crate-masp's exported classes (both steps load it):

- `MaspValidator.prototype.validateCrate` snapshots the profile and target with
  `toJSON()` at call time (tests mutate crates between calls), deep-clones the
  results and labels the case with the outermost test-file frame of the call
  stack plus a per-label sequence number, such as
  `masp-validator.test.js:441 #1`.
- `MaspValidator.prototype.validateEntity` keeps a stack of the
  (class rule, entity) pairs being validated.
- `PropertyRule.prototype.validate` records
  `{class_id, entity_id, property_rule_id, passed}` from the top of that stack.
  Only the first outcome per (class, entity, property rule) is kept, by call
  order, as the JS memo keeps one result per pair.
- `ClassRule.prototype.validateCardinality` records
  `{class_id, passed, valid_count}`.

Batch cases replace the `toJSON()` snapshots with the raw file JSON for both
profile and target, since the Python validator reads raw files.

## Output

| Where | What | Committed |
| --- | --- | --- |
| `tests/fixtures/masp/cases/` | Suite cases, and batch cases built from ro-crate-masp's own profiles and examples or from crategraph's tutorial NT1 | yes |
| `tests/fixtures/masp/profiles/<hash>.json` | Each distinct profile snapshot, once | yes |
| `tests/fixtures/masp/upstream/<name>/` | Verbatim profile crates at the pinned commit | yes |
| `data/masp-parity/cases/` | Cases embedding PARADISEC records or `ldac_examples` corpora (no verified redistribution licence) | no (gitignored) |
| `data/masp-parity/*.json`, `*.log` | Run summaries and logs | no |

Each case file looks like this:

```json
{"label": "masp-validator.test.js:441 #1", "origin": "suite",
 "profile": "profiles/<hash>.json",
 "target": {"...": "crate JSON"},
 "js_test": {"title": "...", "state": "passed"},
 "stack_frames": ["masp-validator.test.js:441"],
 "js_version": {"ro-crate": "3.7.2", "node": "v22.23.3", "ro-crate-masp": "6d7a018..."},
 "js_contexts": {"profile": ["https://w3id.org/ro/crate/1.2/context", "{inline}"], "target": ["..."]},
 "js_results": {"error": [], "success": [], "rules": {}, "ruleFlags": {}},
 "js_outcomes": [{"class_id": "...", "entity_id": "...", "property_rule_id": "...", "passed": true}],
 "js_cardinalities": [{"class_id": "...", "passed": true, "valid_count": 1}],
 "js_is_valid": true}
```

- `profile` is relative to `tests/fixtures/masp/`, for local cases too.
- A case has either `target` (inline JSON) or `target_path` (relative to the
  crategraph repo root). `target_path` is used for crategraph's tutorial NT1,
  for batch self-validation (pointing at `upstream/`) and for suite calls whose
  target is the profile itself.
- `js_outcomes`, `js_cardinalities` and `js_is_valid`
  (`results.error.length === 0`) are the comparison data. `js_results` is the
  raw output, kept for reference.
- `js_test` names the mocha test. For calls made in a `before()` hook, the
  title is the describe block's with `(before all hook)` and `state` is null.
- `js_contexts` lists each crate's `@context` entries (`{inline}` for an
  inline context object).
- `js_exception` appears only if `validateCrate` threw.
- Profile names are the first 12 hex characters of the SHA-256 of the
  profile's canonical JSON. This matches Python's
  `json.dumps(obj, sort_keys=True, separators=(",", ":"))` for this corpus.
  `toJSON()` reorders `@graph`, so a suite snapshot and the raw file of the
  same profile have different names.

## Regeneration notes

- The `owl-to-masp.test.js` cases change on every run, because the converter
  stamps the current time into its generated schema crate (`startTime`).
- Remote JSON-LD contexts are resolved over the network, as for a real user.
  A change upstream could change results.
- `run.sh` deletes `tests/fixtures/masp/cases/`, `tests/fixtures/masp/profiles/`
  and `data/masp-parity/` before each run, so stale cases cannot linger.
- Never read the source of the GPL `ro-crate` npm library. The harness reads
  only the `version` field of its `package.json`.
