#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Copyright 2026, Copyright Owner: Karlsruhe Institute of Technology (KIT)
# Author: Luiz Oliveira
# Contact: luiz.oliveira@kit.edu, Institute for Water and Environment (IWU)

set -euo pipefail

# capiQ reads user_defined/ relative to the project root, so run from there.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Preferred: uv creates or updates .venv from uv.lock, then runs capiQ in it.
if command -v uv >/dev/null 2>&1; then
    exec uv run python -m capiq "$@"
fi

# Fallback without uv: use the virtual-environment Python located in the repository.
# The package must be installed in it: pip install -e .
PYTHON_EXE="$PROJECT_ROOT/.venv/bin/python"

if [ ! -x "$PYTHON_EXE" ]; then
    echo "ERROR: uv was not found and the Python executable does not exist:" >&2
    echo "  \"$PYTHON_EXE\"" >&2
    echo "Install uv (https://docs.astral.sh/uv/) or create .venv and run: pip install -e ." >&2
    exit 1
fi

exec "$PYTHON_EXE" -m capiq "$@"
