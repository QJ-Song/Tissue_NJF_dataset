#!/usr/bin/env bash
set -euo pipefail

ISAACSIM_VERSION="${ISAACSIM_VERSION:-6.0.0.1}"
TORCH_VERSION="${TORCH_VERSION:-2.11.0}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu130}"
INSTALL_EXTSCACHE="${INSTALL_EXTSCACHE:-0}"
export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-300}"
export PIP_RETRIES="${PIP_RETRIES:-10}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_DIR="${WORKSPACE_DIR}/env_isaacsim"

"${SCRIPT_DIR}/check_host.sh"

cd "${WORKSPACE_DIR}"

if [[ ! -f "${ENV_DIR}/bin/activate" ]]; then
  python3.12 -m venv --clear "${ENV_DIR}"
fi

source "${ENV_DIR}/bin/activate"

python -m pip install --upgrade pip
python -m pip install "torch==${TORCH_VERSION}" --index-url "${TORCH_INDEX_URL}"
python -m pip install "isaacsim[all]==${ISAACSIM_VERSION}" --extra-index-url https://pypi.nvidia.com

if [[ "${INSTALL_EXTSCACHE}" == "1" ]]; then
  python -m pip install "isaacsim-extscache-kit==${ISAACSIM_VERSION}" --extra-index-url https://pypi.nvidia.com
fi

python -m pip show isaacsim

cat <<'MSG'

Isaac Sim installation finished.

Next:
  source env_isaacsim/bin/activate
  export OMNI_KIT_ACCEPT_EULA=YES
  isaacsim isaacsim.exp.compatibility_check
  isaacsim

Set OMNI_KIT_ACCEPT_EULA only after reviewing and accepting NVIDIA's Omniverse EULA.

Optional extension cache:
  INSTALL_EXTSCACHE=1 ./scripts/install_isaacsim.sh

The extension cache package is very large and can be skipped for the first run.
MSG
