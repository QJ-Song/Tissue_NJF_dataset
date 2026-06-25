#!/usr/bin/env bash
set -euo pipefail

CONDA_ROOT="${CONDA_ROOT:-$HOME/conda}"
exec "$CONDA_ROOT/bin/conda" run -n sofa python "$@"
