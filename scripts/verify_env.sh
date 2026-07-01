#!/usr/bin/env bash
# Kabul Kapısı -1 (a): araç zinciri sürüm doğrulaması.
set -euo pipefail
source /opt/ros/humble/setup.bash

echo "=========================================================="
echo " GÖKDOĞAN Kabul Kapısı -1 (a) — ortam sürümleri"
echo "=========================================================="

echo -n "[1/4] ros2 (Humble bekleniyor): "
ros2 --help >/dev/null 2>&1 && echo "OK  (ROS_DISTRO=${ROS_DISTRO:-?})" || { echo "FAIL"; exit 1; }
printf '      rosdistro: %s\n' "$ROS_DISTRO"
[ "$ROS_DISTRO" = "humble" ] || { echo "HATA: ROS_DISTRO != humble"; exit 1; }

echo -n "[2/4] colcon: "
colcon version-check >/dev/null 2>&1 || true
colcon --help >/dev/null 2>&1 && echo "OK  ($(python3 -c 'import colcon_core; print(colcon_core.__version__)' 2>/dev/null || echo present))" || { echo "FAIL"; exit 1; }

echo -n "[3/4] sim_vehicle.py --help (ArduPilot SITL): "
sim_vehicle.py --help >/dev/null 2>&1 && echo "OK" || { echo "FAIL"; exit 1; }

echo -n "[4/4] MAVROS paketi: "
ros2 pkg prefix mavros >/dev/null 2>&1 && echo "OK ($(ros2 pkg prefix mavros))" || { echo "FAIL"; exit 1; }

echo -n "      ArduCopter binary: "
command -v arducopter >/dev/null 2>&1 && echo "OK ($(command -v arducopter))" || \
  { ls /opt/ardupilot/build/sitl/bin/arducopter >/dev/null 2>&1 && echo "OK (build/sitl/bin)"; } || \
  { echo "FAIL"; exit 1; }

echo "=========================================================="
echo " Ortam sürüm doğrulaması GEÇTİ ✅"
echo "=========================================================="
