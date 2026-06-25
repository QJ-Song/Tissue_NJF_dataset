#!/usr/bin/env bash
set -euo pipefail

cd "${HOME}/issacsim"
source env_isaacsim/bin/activate
export OMNI_KIT_ACCEPT_EULA=YES
isaacsim isaacsim.exp.compatibility_check
