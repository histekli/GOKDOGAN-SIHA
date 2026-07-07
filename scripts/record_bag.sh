#!/usr/bin/env bash
# rosbag2 kaydı (SAD §22): tüm topic'leri log/ altına kaydeder → post-mortem + test grafiği.
# Kullanım: bash scripts/record_bag.sh [süre_s] [çıktı_dizini]
set -o pipefail
set +u; source /opt/ros/humble/setup.bash
source /workspace/gokdogan-onboard/install/setup.bash 2>/dev/null || true
set -u
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

DUR="${1:-30}"
OUT="${2:-/workspace/log/rosbag_$(date +%Y%m%d_%H%M%S)}"
echo "rosbag2 kaydı → $OUT (${DUR}s, tüm topic'ler)"
timeout "$DUR" ros2 bag record -a -o "$OUT" 2>&1 | tail -5 || true
echo "Kayıt tamam: $OUT"
