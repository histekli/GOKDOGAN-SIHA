#!/usr/bin/env bash
# Kabul Kapısı 1: SITL + onboard graph (MAVROS + mission_fsm + aircraft_state) →
# operatör TAKEOFF komutu → araç OTONOM kalkıp hedef irtifaya çıkıyor, FSM CRUISE'a geçiyor.
# Container içinde koşar (make run-sitl-stack). Workspace build edilmiş olmalı (make ws-build).
set -o pipefail
set +u; source /opt/ros/humble/setup.bash
if [ ! -f /workspace/gokdogan-onboard/install/setup.bash ]; then
  echo "HATA: workspace build edilmemiş. Önce: make ws-build"; exit 1
fi
source /workspace/gokdogan-onboard/install/setup.bash
set -u
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

TARGET_ALT="${TAKEOFF_ALT:-15}"
W=$(mktemp -d /tmp/stack.XXXXXX); cd "$W"

echo "=========================================================="
echo " GÖKDOĞAN Kabul Kapısı 1 — SITL otonom kalkış (hedef ${TARGET_ALT}m)"
echo "=========================================================="

echo "[1/5] ArduCopter SITL başlat"
sim_vehicle.py -v ArduCopter -N -I0 --no-mavproxy --speedup 10 >"$W/sitl.log" 2>&1 &
SITL=$!
cleanup(){ kill $LAUNCH $SITL 2>/dev/null; pkill -f arducopter; pkill -f mavros_node; pkill -f mission_fsm; pkill -f aircraft_state; }
trap cleanup EXIT
for i in $(seq 1 40); do timeout 1 bash -c 'cat </dev/null >/dev/tcp/127.0.0.1/5760' 2>/dev/null && { echo "  tcp:5760 açık"; break; }; sleep 1; done

echo "[2/5] onboard graph launch (competition.launch.py mode:=sitl)"
ros2 launch gokdogan_bringup competition.launch.py mode:=sitl >"$W/launch.log" 2>&1 &
LAUNCH=$!

echo "[3/5] MAVROS connected bekle"
CONN=0
for i in $(seq 1 60); do
  timeout 3 ros2 topic echo --once /mavros/state 2>/dev/null | grep -q "connected: true" && { CONN=1; echo "  connected ($i s)"; break; }
  sleep 1
done
[ "$CONN" = "1" ] || { echo "  BAŞARISIZ: mavros connected olmadı"; tail -20 "$W/launch.log"; exit 1; }

echo "[4/5] operatör komutu: TAKEOFF (SetMissionMode mode=1)"
ros2 service call /mission_fsm/set_mission_mode gokdogan_msgs/srv/SetMissionMode "{mode: 1}" 2>&1 | tail -2

echo "[5/5] otonom kalkış izle (rel_alt + FSM state)"
OK=0
for i in $(seq 1 60); do
  A=$(timeout 3 ros2 topic echo --once --qos-reliability best_effort --qos-durability volatile \
        /mavros/global_position/rel_alt 2>/dev/null | grep -oE "data: [-0-9.]+" | grep -oE "[-0-9]+\.[0-9]+" | head -1)
  S=$(timeout 3 ros2 topic echo --once --qos-durability transient_local \
        /mission/mode 2>/dev/null | grep -oE "state: [0-9]+" | grep -oE "[0-9]+" | head -1)
  echo "  t=$((i*2))s rel_alt=${A:-?} fsm_state=${S:-?}"
  if [ -n "$A" ] && awk "BEGIN{exit !($A>=0.9*$TARGET_ALT)}"; then OK=1; echo "  HEDEF İRTİFA: ${A}m"; fi
  # FSM CRUISE(2) = kalkış tamam
  if [ "${S:-0}" = "2" ]; then echo "  FSM → CRUISE (kalkış tamam)"; OK=1; fi
  [ "$OK" = "1" ] && break
  sleep 2
done

echo "----------------------------------------------------------"
if [ "$OK" = "1" ]; then
  echo " Kabul Kapısı 1 GEÇTİ ✅  (SITL otonom kalkış + FSM CRUISE)"
  exit 0
else
  echo " Kabul Kapısı 1 BAŞARISIZ ❌"; echo "--- launch.log ---"; tail -25 "$W/launch.log"
  exit 1
fi
