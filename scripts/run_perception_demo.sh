#!/usr/bin/env bash
# Kabul Kapısı 3 (ROS grafiği): perception(synthetic,mock) → tracking → lock_validator
# + sahte /aircraft/state (havada+otonom) → /lock/event valid=true üretilmeli.
set -o pipefail
set +u; source /opt/ros/humble/setup.bash
source /workspace/gokdogan-onboard/install/setup.bash
set -u
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
W=$(mktemp -d); cd "$W"

echo "=========================================================="
echo " GÖKDOĞAN Kabul Kapısı 3 (ROS grafiği) — sentetik kilit"
echo "=========================================================="
cleanup(){ pkill -f perception_node; pkill -f tracking_node; pkill -f lock_validator_node; pkill -f "topic pub"; }
trap cleanup EXIT

ros2 run gokdogan_perception perception_node --ros-args -p source:=synthetic -p backend:=mock >"$W/p.log" 2>&1 &
ros2 run gokdogan_tracking tracking_node >"$W/t.log" 2>&1 &
ros2 run gokdogan_lock_validator lock_validator_node >"$W/l.log" 2>&1 &
# Sahte uçak durumu: havada (alt=100) + otonom
ros2 topic pub --qos-reliability best_effort /aircraft/state gokdogan_msgs/msg/AircraftState \
  "{alt: 100.0, is_autonomous: true}" -r 10 >"$W/s.log" 2>&1 &
sleep 3
echo "[graph up] /lock/event izleniyor (valid=true bekleniyor, ~8-10s)"

VALID=0
for i in $(seq 1 20); do
  PROG=$(timeout 2 ros2 topic echo --once /lock/event 2>/dev/null | grep -oE "progress_s: [0-9.]+" | head -1)
  echo "  t=$((i)) ${PROG:-progress?}"
  # Geçerli kilit olayı lock_validator loguna düşer (topic'te progress'ler arasında geçici)
  if grep -q "GEÇERLİ KİLİT" "$W/l.log" 2>/dev/null; then VALID=1; echo "  GEÇERLİ KİLİT üretildi ✅"; break; fi
  sleep 1
done

echo "----------------------------------------------------------"
if [ "$VALID" = "1" ]; then
  echo " Kabul Kapısı 3 (ROS grafiği) GEÇTİ ✅"
  exit 0
else
  echo " BAŞARISIZ ❌ — loglar:"; echo "--- perception ---"; tail -5 "$W/p.log"; echo "--- lock ---"; tail -8 "$W/l.log"
  exit 1
fi
