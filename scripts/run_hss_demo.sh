#!/usr/bin/env bash
# Kabul Kapısı 5 (SITL HSS): SITL + tam graph → TAKEOFF→CRUISE → HSS bölgesi + hedef enjekte →
# mission_fsm SVC_HSS verir → hss_node APF ile hedefe giderken HSS'i İHLAL ETMEZ (0 ihlal).
set -o pipefail
set +u; source /opt/ros/humble/setup.bash
source /workspace/gokdogan-onboard/install/setup.bash
set -u
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
W=$(mktemp -d /tmp/hdemo.XXXXXX); cd "$W"

echo "=========================================================="
echo " GÖKDOĞAN Kabul Kapısı 5 — SITL HSS kaçınma (0 ihlal)"
echo "=========================================================="
cleanup(){ pkill -f arducopter; pkill -f mavros_node; pkill -f mission; pkill -f aircraft_state; pkill -f target_selector; pkill -f guidance; pkill -f hss_node; pkill -f kamikaze; pkill -f "ros2 launch"; pkill -f hss_probe; }
trap cleanup EXIT

sim_vehicle.py -v ArduCopter -N -I0 --no-mavproxy --speedup 3 >"$W/sitl.log" 2>&1 &
for i in $(seq 1 40); do timeout 1 bash -c 'cat </dev/null >/dev/tcp/127.0.0.1/5760' 2>/dev/null && break; sleep 1; done
echo "[1] SITL açık; graph launch (HSS için minimal: guidance/kamikaze kapalı)"
ros2 launch gokdogan_bringup competition.launch.py mode:=sitl \
  enable_guidance:=false enable_kamikaze:=false >"$W/launch.log" 2>&1 &

state(){ timeout 3 ros2 topic echo --once --qos-durability transient_local /mission/mode 2>/dev/null | grep -oE "state: [0-9]+" | grep -oE "[0-9]+" | head -1; }
echo "[2] MAVROS connected bekle"
for i in $(seq 1 60); do timeout 3 ros2 topic echo --once /mavros/state 2>/dev/null | grep -q "connected: true" && break; sleep 1; done
echo "[3] TAKEOFF → CRUISE bekle"
ros2 service call /mission_fsm/set_mission_mode gokdogan_msgs/srv/SetMissionMode "{mode: 1}" >/dev/null 2>&1
CR=0
for i in $(seq 1 60); do S=$(state); [ "${S:-0}" = "2" ] && { CR=1; echo "  → CRUISE"; break; }; sleep 2; done
[ "$CR" = "1" ] || { echo "  BAŞARISIZ: CRUISE yok"; tail -15 "$W/launch.log"; exit 1; }

echo "[4] hss_probe: HSS + hedef enjekte, 0 ihlal izle"
python3 /workspace/scripts/hss_probe.py 2>&1 | tee "$W/probe.log"
RC=${PIPESTATUS[0]}

echo "[5] active_service HSS mi (tahkim) + hss setpoint"
AS=$(timeout 3 ros2 topic echo --once --qos-durability transient_local /mission/mode 2>/dev/null | grep -oE "active_service: [0-9]+" | head -1)
echo "  ${AS:-active_service?}"

echo "----------------------------------------------------------"
MINC=$(grep -oE "min_clearance=[-0-9.]+" "$W/probe.log" | grep -oE "[-0-9.]+" | head -1)
if [ "$RC" = "0" ]; then
  echo " Kabul Kapısı 5 (HSS) GEÇTİ ✅  (0 ihlal: min_clearance=${MINC}m > 0)"
  exit 0
else
  echo " BAŞARISIZ ❌ (min_clearance=${MINC}); launch log:"; tail -12 "$W/launch.log"
  exit 1
fi
