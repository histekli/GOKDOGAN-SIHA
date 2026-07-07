#!/usr/bin/env bash
# GÖRSEL-SERVO demo: kameralı copter (gokdogan_iris_cam) + rakip + QR — tam stack.
#   Gazebo + ArduCopter SITL + MAVROS + mission_fsm kalkışı + YOLO(best.onnx) + tracking.
#   GUI'de izlemek: GZ_HW=1 make run-gorsel-servo          (GZ_HW=1 = host GPU, şart!)
#   Saha dünyası:   GZ_HW=1 WORLD=/workspace/sim/gazebo/worlds/gokdogan_saha.world make run-gorsel-servo
set +u
source /opt/ros/humble/setup.bash; source /workspace/gokdogan-onboard/install/setup.bash
source /usr/share/gazebo/setup.sh 2>/dev/null
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export GAZEBO_PLUGIN_PATH=/workspace/sim/gazebo/ardupilot_gazebo/build:/opt/ros/humble/lib
export GAZEBO_MODEL_PATH=/workspace/sim/gazebo/models:/workspace/sim/gazebo/ardupilot_gazebo/models:/usr/share/gazebo-11/models
export GAZEBO_MODEL_DATABASE_URI=""
WORLD="${WORLD:-/workspace/sim/gazebo/worlds/gokdogan_gorsel_servo.world}"

# Artık-koruması: eski bir koşu (asılı konteyner) SITL portunu tutuyorsa her şey sessizce bozulur
if timeout 1 bash -c 'cat </dev/null >/dev/tcp/127.0.0.1/5760' 2>/dev/null; then
  echo "HATA: 5760 portu zaten dolu — eski bir koşunun artığı çalışıyor (dünkü 'MAVROS bağlı değil' bundandı)."
  echo "      Host'ta:  docker ps   →   docker kill <ID>   (gokdogan-dev konteynerlerini kapat), sonra tekrar dene."
  exit 1
fi

cleanup(){ pkill -f gzserver; pkill -f gazebo; pkill -f arducopter; pkill -f sim_vehicle; pkill -f mavros; pkill -f mission; pkill -f perception; pkill -f tracking; pkill Xvfb; }
trap cleanup EXIT
tani(){ echo "--- TANI: gazebo ---"; grep -iE "error|unable" /workspace/_gs_gz.log 2>/dev/null | grep -ivE "audio|OpenAL|ALSA" | head -3
        echo "--- TANI: SITL ---";  tail -5 /workspace/_gs_sitl.log 2>/dev/null
        echo "--- TANI: launch ---"; grep -iE "error|fail|died" /workspace/_gs_launch.log 2>/dev/null | head -5; }

if [ -n "${DISPLAY:-}" ] && [ -e /tmp/.X11-unix ]; then
  unset QT_QPA_PLATFORM
  if [ "${GZ_HW:-0}" = "1" ]; then
    # imaj ENV'i LIBGL_ALWAYS_SOFTWARE=1 gömer — unset edilmezse GPU verilse bile yazılım render kalır
    unset LIBGL_ALWAYS_SOFTWARE GALLIUM_DRIVER
    [ -e /dev/dri ] || echo "UYARI: GZ_HW=1 ama konteynerde /dev/dri yok → yine yazılım render! (Makefile'daki GPU_DEV satırı güncel mi?)"
  else
    export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe
    echo "UYARI: GUI yazılım render (llvmpipe) ile açılıyor — CPU'yu doyurur, MAVROS kopabilir."
    echo "       Doğrusu:  GZ_HW=1 make run-gorsel-servo"
  fi
  echo "[GUI] gazebo penceresi + rqt_image_view /gokdogan_camera/image_raw ile kamerayı izle"
  gazebo --verbose -s libgazebo_ros_init.so "$WORLD" >/workspace/_gs_gz.log 2>&1 &
else
  export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe QT_QPA_PLATFORM=offscreen
  xvfb-run -a gzserver -s libgazebo_ros_init.so "$WORLD" >/workspace/_gs_gz.log 2>&1 &
fi

echo "[1/5] dünya yükleniyor (kamera topic bekleniyor)..."
OK=0
for i in $(seq 1 120); do
  timeout 2 ros2 topic list 2>/dev/null | grep -q /gokdogan_camera/image_raw && { echo "      dünya hazır (${i}s)"; OK=1; break; }
  [ $((i % 10)) -eq 0 ] && echo "      ... ${i}s (GUI ilk açılışta 1-2 dk normal)"
  sleep 1
done
[ "$OK" = "1" ] || { echo "HATA: dünya 120s içinde hazır olmadı."; tani; exit 1; }
RTF=$(timeout 4 gz stats -p 2>/dev/null | tail -1 | grep -o "^[0-9.]*")
[ -n "$RTF" ] && echo "      gerçek-zaman faktörü: ${RTF} (1.00 = tam hız; <0.5 = kasma → GPU/GZ_HW kontrol et)"

# GUI penceresinin ekrana gelmesi sunucudan yavaştır — izleme payı (WATCH_DELAY=0 ile atla)
if [ -n "${DISPLAY:-}" ] && [ -e /tmp/.X11-unix ]; then
  W="${WATCH_DELAY:-15}"
  [ "$W" -gt 0 ] && { echo "      GUI penceresi için ${W}s izleme payı (WATCH_DELAY ile ayarla)..."; sleep "$W"; }
fi

echo "[2/5] ArduCopter SITL başlıyor..."
sim_vehicle.py -v ArduCopter -f gazebo-iris -N -I0 --no-mavproxy --speedup 1 \
  --add-param-file=/workspace/sim/gazebo/config/gazebo_sitl.param >/workspace/_gs_sitl.log 2>&1 &
OK=0
for i in $(seq 1 60); do
  timeout 1 bash -c 'cat </dev/null >/dev/tcp/127.0.0.1/5760' 2>/dev/null && { echo "      SITL hazır (${i}s)"; OK=1; break; }
  [ $((i % 10)) -eq 0 ] && echo "      ... SITL bekleniyor ${i}s"
  sleep 1
done
[ "$OK" = "1" ] || { echo "HATA: SITL 60s içinde açılmadı."; tani; exit 1; }

echo "[3/5] MAVROS + mission_fsm başlıyor..."
ros2 launch gokdogan_bringup competition.launch.py mode:=sitl \
  enable_guidance:=false enable_hss:=false enable_kamikaze:=false >/workspace/_gs_launch.log 2>&1 &
OK=0
for i in $(seq 1 90); do
  timeout 3 ros2 topic echo --once /mavros/state 2>/dev/null | grep -q "connected: true" && { echo "      MAVROS bağlı (${i}s)"; OK=1; break; }
  [ $((i % 10)) -eq 0 ] && echo "      ... MAVROS bekleniyor ${i}s"
  sleep 1
done
[ "$OK" = "1" ] || { echo "HATA: MAVROS 90s içinde bağlanamadı."; tani; exit 1; }
echo "      EKF oturuyor (15s)..."; sleep 15

echo "[4/5] TAKEOFF komutu (mission_fsm)..."
python3 - <<'PY'
import rclpy, sys, time
from gokdogan_msgs.srv import SetMissionMode
rclpy.init(); n=rclpy.create_node('tk')
c=n.create_client(SetMissionMode,'/mission_fsm/set_mission_mode')
if not c.wait_for_service(timeout_sec=30): print("HATA: servis yok"); sys.exit(1)
for d in range(1,6):
    f=c.call_async(SetMissionMode.Request(mode=1,params_json=''))
    rclpy.spin_until_future_complete(n,f,timeout_sec=20)
    r=f.result()
    if r and r.success: print(f"      TAKEOFF kabul (deneme {d})"); sys.exit(0)
    print(f"      deneme {d}/5 red: {r.message if r else 'cevap yok'} — 8s sonra tekrar",flush=True)
    time.sleep(8)
print("HATA: TAKEOFF 5 denemede kabul edilmedi"); sys.exit(1)
PY
[ $? -eq 0 ] || { tani; exit 1; }

echo "      kalkış izleniyor (FSM settle+arm ~40-60s sürer, hedef 15m — sabır):"
timeout 100 python3 - <<'PY'
import rclpy, time
from std_msgs.msg import Float64
from rclpy.qos import qos_profile_sensor_data
rclpy.init(); n=rclpy.create_node('altmon'); v=[0.0]
n.create_subscription(Float64,'/mavros/global_position/rel_alt',lambda m: v.__setitem__(0,m.data),qos_profile_sensor_data)
t0=time.time(); last=0
while time.time()-t0<95:
    rclpy.spin_once(n,timeout_sec=0.5)
    if v[0]>10.0: print(f"      rel_alt={v[0]:.1f}m — HAVADA ✅",flush=True); break
    if time.time()-last>=5: last=time.time(); print(f"      rel_alt={v[0]:.1f}m",flush=True)
else:
    print("      UYARI: 95s'de 10m'ye ulaşmadı — /mission/mode detail'e bak: ros2 topic echo /mission/mode",flush=True)
PY

echo "[5/5] perception (YOLO best.onnx) + tracking başlıyor"
ros2 run gokdogan_perception perception_node --ros-args -p source:=gazebo -p backend:=onnxruntime \
  -p model_path:=/workspace/docs/best.onnx -p conf:=0.10 -p yolo_every_n:=2 \
  -r /camera/image:=/gokdogan_camera/image_raw &
ros2 run gokdogan_tracking tracking_node &
echo ""
echo "İZLE:  ros2 topic echo /perception/detections   |   ros2 topic echo /perception/tracks"
echo "Bitirmek için Ctrl+C"
wait
