#!/usr/bin/env bash
set -euo pipefail

cd "${HOME}/issacsim"
source env_isaacsim/bin/activate
export OMNI_KIT_ACCEPT_EULA="${OMNI_KIT_ACCEPT_EULA:-YES}"

# Isaac Sim Full enables the ROS 2 bridge by default on Linux. Keep first
# launch independent from ROS so a missing ROS setup does not stop the app.
isaacsim --/isaac/startup/ros_bridge_extension= "$@"
