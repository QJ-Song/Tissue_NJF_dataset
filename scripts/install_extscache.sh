#!/usr/bin/env bash
set -euo pipefail

ISAACSIM_VERSION="${ISAACSIM_VERSION:-6.0.0.1}"
export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-300}"
export PIP_RETRIES="${PIP_RETRIES:-10}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_DIR="${WORKSPACE_DIR}/env_isaacsim"

source "${ENV_DIR}/bin/activate"
python -m pip install "isaacsim-extscache-kit==${ISAACSIM_VERSION}" --extra-index-url https://pypi.nvidia.com

