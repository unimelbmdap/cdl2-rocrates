// Capture hook for the MASP parity harness.
//
// Loaded by mocha (`--require`) when the ro-crate-masp test suite runs, and
// required directly by batch.js. It patches ro-crate-masp's validator classes so
// that every `validateCrate` call is recorded as a parity case:
//
// - `MaspValidator.prototype.validateCrate` snapshots the profile and target
//   crates (via `toJSON()`, taken at call time because tests mutate crates
//   between calls) and deep-clones the results.
// - `MaspValidator.prototype.validateEntity` keeps a stack of the
//   (class rule, entity) pairs being validated.
// - `PropertyRule.prototype.validate` records one structured outcome per
//   (class, entity, property rule), read from the top of that stack.
// - `ClassRule.prototype.validateCardinality` records each class rule's count.
//
// The structured outcomes let the Python parity test compare results without
// parsing message text. Runs inside the container only; see README.md.

"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const MASP_DIR = process.env.MASP_DIR || "/opt/ro-crate-masp";
const MASP_COMMIT = process.env.MASP_COMMIT || "unknown";
const FIXTURES_DIR = process.env.MASP_PARITY_FIXTURES || "/out/fixtures";
const LOCAL_DIR = process.env.MASP_PARITY_LOCAL || "/out/local";

// Suite cases whose targets embed PARADISEC records from ro-crate-masp's
// test_data stay local (no verified licence for redistribution). Matched
// against the mocha test's full title, with a content check as a backstop.
const LOCAL_ONLY_SUITE_TITLES = [/PARADISEC/i];
const LOCAL_ONLY_TARGET_MARKERS = ["catalog.paradisec.org.au/repository/"];

const masp = require(path.join(MASP_DIR, "lib", "masp-validator.js"));
const { MaspValidator, ClassRule, PropertyRule } = masp;

const CAPTURE = Symbol("maspParityCapture");

const state = {
  mode: "suite",
  cases: [],
  labelCounts: new Map(),
  currentTest: null,
  // Cases captured in a before() hook, waiting for the describe's first test.
  hookCases: [],
  tests: [],
};

function deepClone(value) {
  return value === undefined ? null : JSON.parse(JSON.stringify(value));
}

// Canonical JSON for content addressing: sorted keys, compact separators and
// non-ASCII escaped as \uXXXX, matching Python's
// json.dumps(obj, sort_keys=True, separators=(",", ":")) for the JSON in this
// corpus. (Floats such as 1.0 are not distinguishable from 1 once parsed in
// JS, so the hash is a content address, not something Python must recompute.)
function canonicalJson(value) {
  if (value === null || typeof value !== "object") {
    const text = JSON.stringify(value);
    return typeof value === "string"
      ? text.replace(
          /[\u0080-￿]/g,
          (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0")
        )
      : text;
  }
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalJson).join(",") + "]";
  }
  const keys = Object.keys(value).sort();
  return (
    "{" +
    keys.map((k) => canonicalJson(k) + ":" + canonicalJson(value[k])).join(",") +
    "}"
  );
}

function contentHash(value) {
  return crypto
    .createHash("sha256")
    .update(canonicalJson(value), "utf8")
    .digest("hex")
    .slice(0, 12);
}

// The context URLs a crate declares (inline context objects are noted, not
// expanded), so a reader can see which remote contexts each case relied on.
function contextsOf(crateJson) {
  if (!crateJson || typeof crateJson !== "object") return [];
  const raw = crateJson["@context"];
  const items = Array.isArray(raw) ? raw : raw === undefined ? [] : [raw];
  return items.map((c) => (typeof c === "string" ? c : "{inline}"));
}

function snapshot(crate) {
  if (crate && typeof crate.toJSON === "function") return deepClone(crate.toJSON());
  return null;
}

// Label a suite call with the outermost test-file frame of the synchronous
// call stack, so calls made through a helper are labelled by the `it` line.
function callerFrames(stack) {
  const frames = [];
  const re = /\/test\/([^/\s]+\.test\.js):(\d+):\d+/g;
  let m;
  while ((m = re.exec(stack)) !== null) {
    frames.push(`${m[1]}:${m[2]}`);
  }
  return frames;
}

function nextLabel(base) {
  const n = (state.labelCounts.get(base) || 0) + 1;
  state.labelCounts.set(base, n);
  return `${base} #${n}`;
}

// --- Patches ---------------------------------------------------------------

const originalValidateCrate = MaspValidator.prototype.validateCrate;
const originalValidateEntity = MaspValidator.prototype.validateEntity;
const originalPropertyValidate = PropertyRule.prototype.validate;
const originalValidateCardinality = ClassRule.prototype.validateCardinality;

MaspValidator.prototype.validateCrate = async function (targetCrate, options) {
  const limit = Error.stackTraceLimit;
  Error.stackTraceLimit = 200;
  const stack = new Error().stack || "";
  Error.stackTraceLimit = limit;
  const frames = callerFrames(stack);

  // Load the profile first if it is still a path, so its JSON can be snapshot.
  if (!this.profileCrate && this.profileCratePath) this.loadProfileCrate();
  const profileJson = snapshot(this.profileCrate);
  const targetJson =
    typeof targetCrate === "string" ? { "@path": targetCrate } : snapshot(targetCrate);

  const capture = { stack: [], outcomes: [], seen: new Set(), cardinalities: [] };
  this[CAPTURE] = capture;
  let results;
  let jsError = null;
  try {
    results = await originalValidateCrate.call(this, targetCrate, options);
  } catch (error) {
    jsError = String((error && error.stack) || error);
    throw error;
  } finally {
    delete this[CAPTURE];
    const base = frames.length ? frames[frames.length - 1] : "unknown";
    const captured = {
      label: nextLabel(base),
      origin: state.mode,
      stack_frames: frames,
      test: state.currentTest,
      profileJson,
      targetJson,
      results: deepClone(results),
      jsError,
      outcomes: capture.outcomes,
      cardinalities: capture.cardinalities,
    };
    state.cases.push(captured);
    if (state.mode === "suite" && !state.currentTest) state.hookCases.push(captured);
  }
  return results;
};

MaspValidator.prototype.validateEntity = function (entity, classRule) {
  const capture = this[CAPTURE];
  if (!capture) return originalValidateEntity.call(this, entity, classRule);
  capture.stack.push([classRule.id, entity["@id"]]);
  try {
    return originalValidateEntity.call(this, entity, classRule);
  } finally {
    capture.stack.pop();
  }
};

PropertyRule.prototype.validate = function (entity) {
  const capture = this.validator && this.validator[CAPTURE];
  if (!capture) return originalPropertyValidate.call(this, entity);
  const top = capture.stack[capture.stack.length - 1] || [null, entity && entity["@id"]];
  const key = JSON.stringify([top[0], top[1], this.id]);
  // Keep only the first outcome per (class, entity, property rule), reserving
  // its slot at call entry, as the JS memo keeps one result per pair.
  let row = null;
  if (!capture.seen.has(key)) {
    capture.seen.add(key);
    row = { class_id: top[0], entity_id: top[1], property_rule_id: this.id, passed: null };
    capture.outcomes.push(row);
  }
  const passed = originalPropertyValidate.call(this, entity);
  if (row) row.passed = !!passed;
  return passed;
};

ClassRule.prototype.validateCardinality = function (matchCount) {
  const passed = originalValidateCardinality.call(this, matchCount);
  const capture = this.validator && this.validator[CAPTURE];
  if (capture) {
    capture.cardinalities.push({ class_id: this.id, passed: !!passed, valid_count: matchCount });
  }
  return passed;
};

// --- Writing cases ---------------------------------------------------------

function jsVersion() {
  const pkg = JSON.parse(
    fs.readFileSync(path.join(MASP_DIR, "node_modules", "ro-crate", "package.json"), "utf8")
  );
  return { "ro-crate": pkg.version, node: process.version, "ro-crate-masp": MASP_COMMIT };
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 1) + "\n");
}

function writeProfile(profileJson) {
  const name = `profiles/${contentHash(profileJson)}.json`;
  const file = path.join(FIXTURES_DIR, name);
  if (!fs.existsSync(file)) writeJson(file, profileJson);
  return name;
}

function safeName(text) {
  return text.replace(/\.test\.js/, "").replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-|-$/g, "");
}

/**
 * Write one case file. `extra` may override `label`, `origin`, `profileJson`,
 * `target` (raw JSON) or `target_path` (repo-relative path), and `local`.
 * Returns the written path.
 */
function writeCase(captured, extra = {}) {
  const c = { ...captured, ...extra };
  const out = {
    label: c.label,
    origin: c.origin,
    profile: writeProfile(c.profileJson),
  };
  const target = c.target !== undefined ? c.target : c.targetJson;
  if (c.target_path) out.target_path = c.target_path;
  // A profile validating itself: point at the stored profile, not a copy.
  else if (contentHash(target) === contentHash(c.profileJson))
    out.target_path = `tests/fixtures/masp/${out.profile}`;
  else out.target = target;
  if (c.test) out.js_test = { title: c.test.title, state: c.test.state || null };
  if (c.stack_frames && c.origin === "suite") out.stack_frames = c.stack_frames;
  out.js_version = jsVersion();
  out.js_contexts = { profile: contextsOf(c.profileJson), target: contextsOf(target) };
  if (c.jsError) out.js_exception = c.jsError;
  out.js_results = c.results;
  out.js_outcomes = c.outcomes;
  out.js_cardinalities = c.cardinalities;
  out.js_is_valid = c.results ? c.results.error.length === 0 : null;

  const fileName = `${c.fileStem || safeName(c.label)}.json`;
  const dir = c.local ? path.join(LOCAL_DIR, "cases") : path.join(FIXTURES_DIR, "cases");
  const file = path.join(dir, fileName);
  writeJson(file, out);
  return file;
}

function isLocalSuiteCase(captured) {
  const title = (captured.test && captured.test.title) || "";
  if (LOCAL_ONLY_SUITE_TITLES.some((re) => re.test(title))) return true;
  const text = JSON.stringify(captured.targetJson || {});
  return LOCAL_ONLY_TARGET_MARKERS.some((marker) => text.includes(marker));
}

function writeSuiteCases() {
  let committed = 0;
  let local = 0;
  for (const captured of state.cases) {
    const isLocal = isLocalSuiteCase(captured);
    writeCase(captured, { local: isLocal, fileStem: "suite-" + safeName(captured.label) });
    if (isLocal) local++;
    else committed++;
  }
  const failed = state.tests.filter((t) => t.state === "failed");
  const summary = {
    suite_cases: state.cases.length,
    committed,
    local,
    tests: state.tests.length,
    tests_passed: state.tests.filter((t) => t.state === "passed").length,
    tests_failed: failed.map((t) => t.title),
    tests_other: state.tests.filter((t) => t.state !== "passed" && t.state !== "failed").map((t) => t.title),
  };
  writeJson(path.join(LOCAL_DIR, "suite-summary.json"), summary);
  console.log("\n[masp-parity] suite summary " + JSON.stringify(summary, null, 2));
}

// --- Mocha root hooks (suite mode only) -----------------------------------

const mochaHooks = {
  beforeEach() {
    const test = this.currentTest;
    const file = path.basename(test.file || "");
    const record = { title: test.fullTitle(), file, state: null };
    // A before() hook runs just ahead of its describe's first test; name its
    // cases after that describe (state stays null: hooks have no test result).
    for (const captured of state.hookCases.splice(0)) {
      if (captured.label.startsWith(file + ":")) {
        captured.test = { title: `${test.parent.fullTitle()} (before all hook)`, state: null };
      }
    }
    state.tests.push(record);
    state.currentTest = record;
  },
  afterEach() {
    if (state.currentTest) state.currentTest.state = this.currentTest.state || null;
    state.currentTest = null;
  },
  afterAll() {
    if (state.mode === "suite") writeSuiteCases();
  },
};

module.exports = {
  mochaHooks,
  state,
  canonicalJson,
  contentHash,
  jsVersion,
  writeCase,
  writeJson,
  setMode(mode) {
    state.mode = mode;
  },
  takeLastCase() {
    return state.cases.pop();
  },
};
