#!/usr/bin/env bash
# Kabul Kapısı 8 (SITL Failsafe): SITL + onboard → CRUISE, sonra:
#   [A] GCS/telemetri kaybı DEBOUNCE: /failsafe/gcs_ok=false <10s → RTL tetiklenMEZ (yanlış-tetik yok)
#   [B] node-crash: aircraft_state_node öldür → watchdog bayat → mission_fsm RTL (güvenli state)
#   + yapısal JSON log (JSONLOG) + /health/status yayını doğrulanır.
set -o pipefail
set +u; source /opt/ros/humble/setup.bash
source /workspace/gokdogan-onboard/install/setup.bash
set -u
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
W=$(mktemp -d /tmp/fsdemo.XXXXXX); cd "$W"

echo "=========================================================="
echo " GÖKDOĞAN Kabul Kapısı 8 — Failsafe & Watchdog (SITL)"
echo "=========================================================="
cleanup(){ pkill -f arducopter; pkill -f mavros_node; pkill -f mission; pkill -f aircraft_state;
           pkill -f "ros2 launch"; pkill -f "ros2 topic"; }
trap cleanup EXIT

echo "[1] SITL (ArduCopter, speedup 3)"
sim_vehicle.py -v ArduCopter -N -I0 --no-mavproxy --speedup 3 >"$W/sitl.log" 2>&1 &
for i in $(seq 1 40); do timeout 1 bash -c 'cat </dev/null >/dev/tcp/127.0.0.1/5760' 2>/dev/null && break; sleep 1; done

echo "[2] onboard graph (fsm + mission_link + aircraft_state; guidance/hss/kamikaze kapalı)"
ros2 launch gokdogan_bringup competition.launch.py mode:=sitl \
  enable_guidance:=false enable_hss:=false enable_kamikaze:=false >"$W/launch.log" 2>&1 &

state(){ timeout 3 ros2 topic echo --once --qos-durability transient_local /mission/mode 2>/dev/null | grep -oE "state: [0-9]+" | grep -oE "[0-9]+" | head -1; }
echo "[3] MAVROS connected bekle"
for i in $(seq 1 60); do timeout 3 ros2 topic echo --once /mavros/state 2>/dev/null | grep -q "connected: true" && break; sleep 1; done
echo "[4] TAKEOFF → CRUISE bekle"
ros2 service call /mission_fsm/set_mission_mode gokdogan_msgs/srv/SetMissionMode "{mode: 1}" >/dev/null 2>&1
CR=0
for i in $(seq 1 60); do S=$(state); [ "${S:-0}" = "2" ] && { CR=1; echo "  → CRUISE"; break; }; sleep 2; done
[ "$CR" = "1" ] || { echo "  BAŞARISIZ: CRUISE yok"; tail -15 "$W/launch.log"; exit 1; }

echo "[5][A] DEBOUNCE: /failsafe/gcs_ok=false 6s (<10s eşik) → RTL tetiklenMEMELİ"
( for i in $(seq 1 12); do ros2 topic pub --once /failsafe/gcs_ok std_msgs/msg/Bool "{data: false}" >/dev/null 2>&1; sleep 0.5; done ) &
sleep 6
S_DB=$(state); echo "  debounce sırasında state=$S_DB (2=CRUISE beklenir)"
# gcs_ok'i geri sağlıklıya al (latch yok çünkü henüz tetiklenmedi)
ros2 topic pub --once /failsafe/gcs_ok std_msgs/msg/Bool "{data: true}" >/dev/null 2>&1
sleep 1
DB_OK=0; [ "${S_DB:-0}" = "2" ] && DB_OK=1

echo "[6][B] NODE-CRASH: aircraft_state_node öldür → watchdog(3s) → mission_fsm RTL"
pkill -f aircraft_state_node
RTL=0
for i in $(seq 1 20); do S=$(state); [ "${S:-0}" = "5" ] && { RTL=1; echo "  → RTL (state=5)"; break; }; sleep 1; done

echo "[7] MAVROS modu + /health/status + yapısal log doğrula"
MODE=$(timeout 3 ros2 topic echo --once /mavros/state 2>/dev/null | grep -oE "mode: \"?[A-Z_]+" | head -1)
echo "  mavros $MODE"
HEALTH=$(timeout 3 ros2 topic echo --once /health/status std_msgs/msg/String 2>/dev/null | grep -oE "data: .*" | head -1)
echo "  ${HEALTH:-health/status?}"
JLOG=$(grep -oE "JSONLOG .*failsafe.*" "$W/launch.log" | tail -1)
echo "  ${JLOG:-JSONLOG(failsafe)?}"

echo "----------------------------------------------------------"
OK=1
[ "$DB_OK" = "1" ] && echo "  ✅ debounce: <10s GCS-loss RTL tetiklemedi (CRUISE korundu)" || { echo "  ❌ debounce: erken RTL"; OK=0; }
[ "$RTL" = "1" ] && echo "  ✅ node-crash → watchdog → mission_fsm RTL (güvenli state)" || { echo "  ❌ node-crash sonrası RTL yok"; OK=0; }
echo "$MODE" | grep -q "RTL" && echo "  ✅ MAVROS RTL moduna geçti" || echo "  ⚠️  MAVROS modu RTL değil ($MODE)"
echo "$HEALTH" | grep -q "stale=\['aircraft_state'\]" && echo "  ✅ /health/status aircraft_state bayat gösterdi" || echo "  ⚠️  health stale listesi beklenen değil"
[ -n "$JLOG" ] && echo "  ✅ yapısal JSON failsafe log üretildi" || { echo "  ❌ JSONLOG failsafe yok"; OK=0; }
echo "----------------------------------------------------------"
if [ "$OK" = "1" ]; then
  echo " Kabul Kapısı 8 (Failsafe) GEÇTİ ✅"; exit 0
else
  echo " BAŞARISIZ ❌"; tail -15 "$W/launch.log"; exit 1
fi
