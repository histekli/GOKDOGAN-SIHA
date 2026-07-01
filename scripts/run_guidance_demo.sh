#!/usr/bin/env bash
# Kabul Kapısı 4 (SITL kaba faz): SITL + tam graph (target_selector + guidance) →
# TAKEOFF→CRUISE → rakip enjekte + LOCKING → guidance rakibe YAKLAŞIR (mesafe azalır).
set -o pipefail
set +u; source /opt/ros/humble/setup.bash
source /workspace/gokdogan-onboard/install/setup.bash
set -u
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
W=$(mktemp -d /tmp/gdemo.XXXXXX); cd "$W"

echo "=========================================================="
echo " GÖKDOĞAN Kabul Kapısı 4 — SITL kaba-faz yaklaşım"
echo "=========================================================="
cleanup(){ pkill -f arducopter; pkill -f mavros_node; pkill -f mission_fsm; pkill -f mission_link; pkill -f aircraft_state; pkill -f target_selector; pkill -f guidance; pkill -f "ros2 launch"; pkill -f guidance_probe; }
trap cleanup EXIT

sim_vehicle.py -v ArduCopter -N -I0 --no-mavproxy --speedup 10 >"$W/sitl.log" 2>&1 &
for i in $(seq 1 40); do timeout 1 bash -c 'cat </dev/null >/dev/tcp/127.0.0.1/5760' 2>/dev/null && break; sleep 1; done
echo "[1] SITL açık; graph launch"
ros2 launch gokdogan_bringup competition.launch.py mode:=sitl >"$W/launch.log" 2>&1 &

state(){ timeout 3 ros2 topic echo --once --qos-durability transient_local /mission/mode 2>/dev/null | grep -oE "state: [0-9]+" | grep -oE "[0-9]+" | head -1; }
echo "[2] MAVROS connected bekle"
for i in $(seq 1 60); do timeout 3 ros2 topic echo --once /mavros/state 2>/dev/null | grep -q "connected: true" && break; sleep 1; done

echo "[3] TAKEOFF → CRUISE bekle"
ros2 service call /mission_fsm/set_mission_mode gokdogan_msgs/srv/SetMissionMode "{mode: 1}" >/dev/null 2>&1
CR=0
for i in $(seq 1 60); do S=$(state); [ "${S:-0}" = "2" ] && { CR=1; echo "  → CRUISE"; break; }; sleep 2; done
[ "$CR" = "1" ] || { echo "  BAŞARISIZ: CRUISE yok"; tail -15 "$W/launch.log"; exit 1; }

echo "[4] guidance_probe: rakip enjekte + LOCKING + yaklaşma izle"
python3 /workspace/scripts/guidance_probe.py 2>&1 | tee "$W/probe.log"
RC=${PIPESTATUS[0]}

echo "[5] guidance setpoint yazıyor mu (tek-yazıcı, LOCKING'te)"
SPLAT=$(timeout 4 ros2 topic echo --once --qos-reliability best_effort /mavros/setpoint_raw/global 2>/dev/null | grep -oE "latitude: [-0-9.]+" | head -1)
echo "  ${SPLAT:-setpoint yok}"

echo "----------------------------------------------------------"
D0=$(grep -oE "d0=[0-9.]+" "$W/probe.log" | grep -oE "[0-9.]+" | head -1)
DMIN=$(grep -oE "dmin=[0-9.]+" "$W/probe.log" | grep -oE "[0-9.]+" | head -1)
if [ "$RC" = "0" ]; then
  echo " Kabul Kapısı 4 (kaba faz) GEÇTİ ✅  (yaklaşma: d0=${D0}m → dmin=${DMIN}m)"
  exit 0
else
  echo " BAŞARISIZ ❌ (d0=${D0} dmin=${DMIN}); guidance log:"; tail -12 "$W/launch.log"
  exit 1
fi
