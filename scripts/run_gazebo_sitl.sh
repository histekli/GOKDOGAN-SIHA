#!/usr/bin/env bash
# Adım 4a — ardupilot_gazebo kenetleme entegrasyon testi:
#   Gazebo(iris + ArduPilotPlugin) ↔ ArduCopter SITL(gazebo-iris frame) ↔ MAVROS ↔ mission_fsm.
#   Kanıtlanmış stack (Faz 1) ile: operatör TAKEOFF → araç GAZEBO FİZİĞİNDE otonom kalkar → FSM CRUISE.
#   Gerçek-zaman (speedup 1) → prearm/EKF settle için timeout'lar cömert. GPU'suz (llvmpipe).
set -o pipefail
set +u
source /opt/ros/humble/setup.bash
source /workspace/gokdogan-onboard/install/setup.bash 2>/dev/null || { echo "HATA: workspace build edilmemiş"; exit 1; }
source /usr/share/gazebo/setup.sh 2>/dev/null || source /usr/share/gazebo-11/setup.sh 2>/dev/null
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export GAZEBO_PLUGIN_PATH=/workspace/sim/gazebo/ardupilot_gazebo/build:/opt/ros/humble/lib
export GAZEBO_MODEL_PATH=/workspace/sim/gazebo/ardupilot_gazebo/models:/workspace/sim/gazebo/models:/usr/share/gazebo-11/models
export GAZEBO_MODEL_DATABASE_URI=""   # KRİTİK: ölü online model DB'yi kapat → gzserver takılmaz,
                                      # aksi halde model fetch'te asılıp ArduPilotPlugin YÜKLENMEZ (9002 açılmaz)
export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe QT_QPA_PLATFORM=offscreen

WORLD=/workspace/sim/gazebo/ardupilot_gazebo/worlds/iris_arducopter_runway.world
TARGET_ALT="${TAKEOFF_ALT:-15}"
W=$(mktemp -d /tmp/gzsitl.XXXXXX)
RESULT="${RESULT_FILE:-/workspace/_gzsitl_result.txt}"; : > "$RESULT"
log(){ echo "$@"; echo "$@" >> "$RESULT"; }

cleanup(){ mkdir -p /workspace/_gzsitl_logs; cp "$W"/*.log /workspace/_gzsitl_logs/ 2>/dev/null;
  pkill -f gzserver; pkill -f arducopter; pkill -f sim_vehicle; pkill -f mavros_node; pkill -f mission_fsm; pkill -f aircraft_state; pkill Xvfb; }
trap cleanup EXIT

log "=== Adım 4a: Gazebo↔SITL↔MAVROS↔mission_fsm kenetleme (hedef ${TARGET_ALT}m) ==="

log "[1] gzserver (iris + ArduPilotPlugin, headless llvmpipe)"
xvfb-run -a -s "-screen 0 1280x1024x24" gzserver "$WORLD" >"$W/gz.log" 2>&1 &
sleep 10
grep -qiE "Unable to start|Address already" "$W/gz.log" && { log "  ❌ GAZEBO_BIND_FAIL (lingering gazebo?)"; exit 1; }

log "[2] ArduCopter SITL (gazebo-iris frame, speedup 1)"
sim_vehicle.py -v ArduCopter -f gazebo-iris -N -I0 --no-mavproxy --speedup 1 >"$W/sitl.log" 2>&1 &
for i in $(seq 1 40); do timeout 1 bash -c 'cat </dev/null >/dev/tcp/127.0.0.1/5760' 2>/dev/null && { log "  tcp:5760 açık ($i s)"; break; }; sleep 1; done

log "[3] onboard graph (MAVROS + mission_fsm + aircraft_state)"
ros2 launch gokdogan_bringup competition.launch.py mode:=sitl \
  enable_guidance:=false enable_hss:=false enable_kamikaze:=false >"$W/launch.log" 2>&1 &

log "[4] MAVROS connected + GPS fix bekle"
CONN=0
for i in $(seq 1 60); do
  timeout 3 ros2 topic echo --once /mavros/state 2>/dev/null | grep -q "connected: true" && { CONN=1; log "  MAVROS connected ($i s)"; break; }
  sleep 1
done
[ "$CONN" = "1" ] || { log "  ❌ MAVROS connected olmadı"; tail -15 "$W/launch.log" | sed 's/^/    /'; exit 1; }
# GPS fix (gazebo kenetlemede GPS gerçekten geliyor mu — MAVROS düzgün stream ister)
for i in $(seq 1 40); do
  FIX=$(timeout 3 ros2 topic echo --once /mavros/global_position/raw/fix 2>/dev/null | grep -oE "status: [-0-9]+" | head -1 | grep -oE "[-0-9]+")
  [ -n "$FIX" ] && [ "$FIX" -ge 0 ] 2>/dev/null && { log "  GPS fix status=$FIX ($((i*2))s)"; break; }
  sleep 2
done

log "[5] operatör TAKEOFF (SetMissionMode mode=1) — mission_fsm prearm settle + arm + takeoff"
ros2 service call /mission_fsm/set_mission_mode gokdogan_msgs/srv/SetMissionMode "{mode: 1}" >/dev/null 2>&1

log "[6] otonom kalkış izle (rel_alt + FSM), gerçek-zaman ~90s"
OK=0
for i in $(seq 1 60); do
  A=$(timeout 3 ros2 topic echo --once --qos-reliability best_effort --qos-durability volatile \
        /mavros/global_position/rel_alt 2>/dev/null | grep -oE "data: [-0-9.]+" | grep -oE "[-0-9]+\.[0-9]+" | head -1)
  S=$(timeout 3 ros2 topic echo --once --qos-durability transient_local \
        /mission/mode 2>/dev/null | grep -oE "state: [0-9]+" | grep -oE "[0-9]+" | head -1)
  log "  t=$((i*3))s rel_alt=${A:-?} fsm_state=${S:-?}"
  if [ -n "$A" ] && awk "BEGIN{exit !($A>=0.85*$TARGET_ALT)}" 2>/dev/null; then OK=1; log "  ✅ HEDEF İRTİFA ${A}m (GAZEBO fiziğinde)"; break; fi
  [ "${S:-0}" = "2" ] && { OK=1; log "  ✅ FSM → CRUISE (kalkış tamam)"; break; }
  sleep 3
done

log "----------------------------------------------------------"
if [ "$OK" = "1" ]; then log " ADIM 4a GEÇTİ ✅  (stack Gazebo fiziğinde otonom kalktı)"; exit 0
else log " ADIM 4a BAŞARISIZ ❌"; log "--- sitl.log son 10 ---"; tail -10 "$W/sitl.log" | sed 's/^/    /'; exit 1; fi
