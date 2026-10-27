#!/usr/bin/env bash
# Python RemotionProps → remotion/src/generated/props.ts
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out_dir="${1:-$root/remotion/src/generated}"
mkdir -p "$out_dir"
(cd "$root" && uv run python -m md2short.schema_export) > "$out_dir/props.schema.json"
(cd "$root/remotion" && pnpm exec json2ts -i "$out_dir/props.schema.json" -o "$out_dir/props.ts" \
  --bannerComment "/* Generated from md2short.schema.RemotionProps by scripts/gen_types.sh. Do not edit. */")
