#!/bin/bash
# Render named views of the CURRENT revision of $DECO_SESSION through the MCP server and print the PNG paths.
# usage: DECO_SESSION=name scripts/deco_views.sh [--lighting dusk|night|day|off] view1 view2 ...   (views: see `status`)
cd "$(dirname "$0")/.." || exit 1
source scripts/_python.sh
L=dusk; if [ "$1" = "--lighting" ]; then L=$2; shift 2; fi
args=(); for v in "$@"; do args+=(render "{\"view\":\"$v\",\"width\":1000,\"height\":667,\"lighting\":\"$L\"}"); done
out=$(mktemp) || exit 1
trap 'rm -f "$out"' EXIT
timeout 500 "$PYTHON" scripts/deco_mcp_client.py call "${args[@]}" > "$out" 2>&1
status=$?
grep -o '"image": "[^"]*"' "$out" | sed 's/\\/\//g; s/"image": //; s/"//g'
grep -n "isError=True" -A2 "$out"
grep -o '"outside_floor": \[[^]]*\]' "$out" | head -1

exit "$status"
