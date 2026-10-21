#!/usr/bin/env bash
# Build the MASP parity image and regenerate the captured JS reference cases.
# Committed output: tests/fixtures/masp/{cases,profiles,upstream,LICENSE}.
# Local-only output (gitignored): data/masp-parity/.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
image="crategraph-masp-parity"
fixtures="$repo/tests/fixtures/masp"
local_dir="$repo/data/masp-parity"
tutorial_nt1="docs/tutorials/data/paradisec/NT1"

docker build -t "$image" "$here"

# Start from a clean slate so stale cases from earlier runs cannot linger.
rm -rf "$fixtures/cases" "$fixtures/profiles" "$local_dir"
mkdir -p "$fixtures" "$local_dir"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$fixtures:/out/fixtures" \
  -v "$local_dir:/out/local" \
  -v "$repo/$tutorial_nt1:/crategraph/$tutorial_nt1:ro" \
  "$image"

for summary in suite-summary.json batch-summary.json; do
  if [[ ! -f "$local_dir/$summary" ]]; then
    echo "run.sh: $summary was not written; see $local_dir/*.log" >&2
    exit 1
  fi
done

committed=$(find "$fixtures/cases" -name '*.json' | wc -l | tr -d ' ')
local_only=$(find "$local_dir/cases" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
profiles=$(find "$fixtures/profiles" -name '*.json' | wc -l | tr -d ' ')
echo "masp-parity: $committed committed cases, $local_only local-only cases, $profiles profile snapshots"
du -sh "$fixtures"
