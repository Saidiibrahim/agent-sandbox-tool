#!/usr/bin/env bash
set -euo pipefail

node scripts/execplan/validate-state.mjs

legacy_hidden_dir="agent"
legacy_hidden_pattern="\\.${legacy_hidden_dir}/"
if git grep -n "$legacy_hidden_pattern" -- . >/dev/null 2>&1; then
  echo "Legacy hidden planning path detected in tracked files."
  git grep -n "$legacy_hidden_pattern" -- .
  exit 1
fi

legacy_spec_segment="specs"
legacy_spec_pattern="\\b${legacy_spec_segment}/"
legacy_product_specs_glob="docs/product-${legacy_spec_segment}/**"
if git grep -n "$legacy_spec_pattern" -- . ":(exclude)${legacy_product_specs_glob}" >/dev/null 2>&1; then
  echo "Legacy spec path detected outside the product specs directory."
  git grep -n "$legacy_spec_pattern" -- . ":(exclude)${legacy_product_specs_glob}"
  exit 1
fi

python3 - <<'PY'
import os
import pathlib
import re
import sys

repo = pathlib.Path.cwd()
link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
bad = []

for rel_path in os.popen("git ls-files '*.md'").read().splitlines():
    file_path = repo / rel_path
    text = file_path.read_text(encoding="utf-8")
    for match in link_re.finditer(text):
        target = match.group(1).strip()
        if not target or target.startswith("#"):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        if target.startswith("/"):
            continue
        target_path = target.split("#", 1)[0]
        if not target_path:
            continue
        resolved = (file_path.parent / target_path).resolve()
        if not resolved.exists():
            bad.append(f"{rel_path}: missing link target {target}")

if bad:
    print("Broken local markdown links detected:")
    for line in bad:
        print(line)
    sys.exit(1)
PY
