// Batch run of the MASP parity harness: validates real profile/crate pairs
// listed in pairs.json with the JS validator and writes one case per pair.
//
// It also refreshes tests/fixtures/masp/upstream/ (verbatim profile crates) and
// tests/fixtures/masp/LICENSE from the pinned ro-crate-masp clone.
// Runs inside the container only; see README.md.

"use strict";

const fs = require("fs");
const path = require("path");

const hook = require("./capture-hook.js");

const MASP_DIR = process.env.MASP_DIR || "/opt/ro-crate-masp";
const CRATEGRAPH_DIR = process.env.CRATEGRAPH_DIR || "/crategraph";
const FIXTURES_DIR = process.env.MASP_PARITY_FIXTURES || "/out/fixtures";
const LOCAL_DIR = process.env.MASP_PARITY_LOCAL || "/out/local";

const { ROCrate } = require(require.resolve("ro-crate", { paths: [MASP_DIR] }));
const { MaspValidator } = require(path.join(MASP_DIR, "lib", "masp-validator.js"));

function resolvePath(spec) {
  const [root, rel] = spec.split(/:(.*)/s);
  const base = { masp: MASP_DIR, crategraph: CRATEGRAPH_DIR }[root];
  if (!base) throw new Error(`Unknown path root in ${spec}`);
  return path.join(base, rel);
}

function profilePath(name) {
  return path.join(MASP_DIR, "profiles", name, "profile-crate", "ro-crate-metadata.json");
}

// Expand one '*' path segment into every matching directory, returning
// [dirName, path] pairs (dirName is null when there is no '*').
function expand(file) {
  const parts = file.split(path.sep);
  const star = parts.indexOf("*");
  if (star === -1) return [[null, file]];
  const parent = parts.slice(0, star).join(path.sep) || path.sep;
  return fs
    .readdirSync(parent, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .sort()
    .map((dir) => [dir, [...parts.slice(0, star), dir, ...parts.slice(star + 1)].join(path.sep)])
    .filter(([, p]) => fs.existsSync(p));
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function refreshUpstream(names) {
  for (const name of names) {
    const dest = path.join(FIXTURES_DIR, "upstream", name, "ro-crate-metadata.json");
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(profilePath(name), dest);
  }
  fs.copyFileSync(path.join(MASP_DIR, "LICENSE"), path.join(FIXTURES_DIR, "LICENSE"));
}

async function runPair(name, targetFile, pair) {
  const profileJson = readJson(profilePath(pair.profile));
  const targetJson = readJson(targetFile);
  // validateCrate needs crate objects: given a path it calls resolveContext()
  // on the string before reaching its own path branch.
  const profileCrate = new ROCrate(readJson(profilePath(pair.profile)), { array: true, link: true });
  const targetCrate = new ROCrate(readJson(targetFile), { array: true, link: true });
  await new MaspValidator(profileCrate).validateCrate(targetCrate);
  const captured = hook.takeLastCase();
  const extra = {
    label: `batch:${name}`,
    origin: "batch",
    fileStem: `batch-${name}`,
    // Raw files, not toJSON() output, for the Python side.
    profileJson,
    local: pair.store === "local",
  };
  if (pair.target_path) extra.target_path = pair.target_path;
  else extra.target = targetJson;
  return { file: hook.writeCase(captured, extra), captured };
}

async function main() {
  const config = readJson(path.join(__dirname, "pairs.json"));
  hook.setMode("batch");
  refreshUpstream(config.upstream_profiles);

  const summary = { batch_cases: 0, committed: 0, local: 0, errored: [], cases: [] };
  for (const pair of config.pairs) {
    for (const [dir, targetFile] of expand(resolvePath(pair.target))) {
      const name = pair.name.replace("{dir}", dir || "");
      try {
        const { file, captured } = await runPair(name, targetFile, pair);
        summary.batch_cases++;
        summary[pair.store === "local" ? "local" : "committed"]++;
        summary.cases.push({
          name,
          file: path.relative("/out", file),
          errors: captured.results ? captured.results.error.length : null,
          outcomes: captured.outcomes.length,
        });
      } catch (error) {
        summary.errored.push({ name, error: String((error && error.stack) || error) });
      }
    }
  }
  hook.writeJson(path.join(LOCAL_DIR, "batch-summary.json"), summary);
  console.log("\n[masp-parity] batch summary " + JSON.stringify(summary, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
