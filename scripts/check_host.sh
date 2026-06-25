#!/usr/bin/env bash
set -euo pipefail

echo "Host: $(hostname)"
echo "Kernel: $(uname -a)"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: Isaac Sim local installation requires Linux or Windows. This script targets Ubuntu Linux."
  exit 1
fi

if [[ "$(uname -m)" != "x86_64" ]]; then
  echo "ERROR: This installer expects x86_64."
  exit 1
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  echo "OS: ${PRETTY_NAME:-unknown}"
  if [[ "${ID:-}" != "ubuntu" || ( "${VERSION_ID:-}" != "24.04" && "${VERSION_ID:-}" != "22.04" ) ]]; then
    echo "ERROR: Isaac Sim supports Ubuntu 22.04/24.04 for x86_64 Linux."
    exit 1
  fi
else
  echo "ERROR: Cannot read /etc/os-release."
  exit 1
fi

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "ERROR: python3.12 is required."
  exit 1
fi
python3.12 --version

if ! python3.12 -m venv --help >/dev/null 2>&1; then
  echo "ERROR: python3.12 venv support is missing. Install it with: sudo apt install python3.12-venv"
  exit 1
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi was not found. Install the NVIDIA driver first."
  exit 1
fi
nvidia-smi

echo "Host checks passed."
