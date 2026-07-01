#!/usr/bin/env bash
# Kabul Kapısı 2 capstone: SITL + tam graph (mission_link dahil) → TAKEOFF→CRUISE →
# mock_gcs START_LOCK gönderir → FSM LOCKING'e geçer + mock_gcs aircraft_vision alır.
set -o pipefail
set +u; source /opt/ros/humble/setup.bash
source /workspace/gokdogan-onboard/install/setup.bash
set -u
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
W=$(mktemp -d /tmp/mldemo.XXXXXX); cd "$W"

echo "=========================================================="
echo " GÖKDOĞAN Kabul Kapısı 2 — mission_link uçtan uca (START_LOCK→LOCKING)"
echo "=========================================================="

sim_vehicle.py -v ArduCopter -N -I0 --no-mavproxy --speedup 10 >"$W/sitl.log" 2>&1 &
cleanup(){ pkill -f arducopter; pkill -f mavros_node; pkill -f mission_fsm; pkill -f mission_link; pkill -f aircraft_state; pkill -f "ros2 launch"; }
trap cleanup EXIT
for i in $(seq 1 40); do timeout 1 bash -c 'cat </dev/null >/dev/tcp/127.0.0.1/5760' 2>/dev/null && break; sleep 1; done
echo "[1] SITL tcp:5760 açık; graph launch"
ros2 launch gokdogan_bringup competition.launch.py mode:=sitl >"$W/launch.log" 2>&1 &

state(){ timeout 3 ros2 topic echo --once --qos-durability transient_local /mission/mode 2>/dev/null | grep -oE "state: [0-9]+" | grep -oE "[0-9]+" | head -1; }

echo "[2] MAVROS connected bekle"
for i in $(seq 1 60); do timeout 3 ros2 topic echo --once /mavros/state 2>/dev/null | grep -q "connected: true" && { echo "  connected"; break; }; sleep 1; done

echo "[3] TAKEOFF (servis) → CRUISE bekle"
ros2 service call /mission_fsm/set_mission_mode gokdogan_msgs/srv/SetMissionMode "{mode: 1}" >/dev/null 2>&1
CRUISE=0
for i in $(seq 1 60); do S=$(state); echo "  t=$((i*2)) fsm_state=${S:-?}"; [ "${S:-0}" = "2" ] && { CRUISE=1; echo "  → CRUISE"; break; }; sleep 2; done
[ "$CRUISE" = "1" ] || { echo "  BAŞARISIZ: CRUISE'a ulaşılamadı"; tail -15 "$W/launch.log"; exit 1; }

echo "[4] mock_gcs bağlan + START_LOCK gönder (+server_data)"
SUM=$(python3 /workspace/tools/mock_gcs.py --host 127.0.0.1 --duration 7 --start-lock-after 1 --server-data --summary 2>/dev/null | grep MOCK_GCS_SUMMARY)
echo "  $SUM"

echo "[5] FSM LOCKING (state=3) mı"
LOCK=0
for i in $(seq 1 10); do S=$(state); echo "  fsm_state=${S:-?}"; [ "${S:-0}" = "3" ] && { LOCK=1; break; }; sleep 1; done

echo "----------------------------------------------------------"
VIS=$(echo "$SUM" | grep -oE '"vision_count": [0-9]+' | grep -oE "[0-9]+")
if [ "$LOCK" = "1" ] && [ "${VIS:-0}" -gt 0 ]; then
  echo " Kabul Kapısı 2 GEÇTİ ✅  (START_LOCK→LOCKING + aircraft_vision alındı: ${VIS} paket)"
  exit 0
else
  echo " Kabul Kapısı 2 BAŞARISIZ ❌ (LOCKING=$LOCK vision=${VIS:-0})"; tail -15 "$W/launch.log"; exit 1
fi
