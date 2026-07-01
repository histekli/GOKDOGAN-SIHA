#!/usr/bin/env bash
# GÖKDOĞAN dev container entrypoint — ROS2 Humble + ArduPilot ortamını hazırlar.
set -e

# ROS2 Humble
source /opt/ros/humble/setup.bash

# colcon workspace (build edilmişse overlay'i kaynakla)
if [ -f /workspace/gokdogan-onboard/install/setup.bash ]; then
  source /workspace/gokdogan-onboard/install/setup.bash
fi

# DDS lokal (İ4 / C5) — yarışma ağında keşif denenmez
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-1}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"

exec "$@"
