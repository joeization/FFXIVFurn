#!/bin/bash
# usage: DECO_SESSION=name scripts/deco_call.sh <tool> '<json or @file.json>' [<tool> '<json>' ...]   (prints MCP results; large outputs are saved by the harness)
set -o pipefail
cd "$(dirname "$0")/.." || exit 1
source scripts/_python.sh
timeout 500 "$PYTHON" scripts/deco_mcp_client.py call "$@" 2>&1 | grep -v "^Processing request"
