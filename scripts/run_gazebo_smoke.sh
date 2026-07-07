#!/usr/bin/env bash
# Gazebo Adım 1 — kamera-in-the-loop smoke:
#   Gazebo Classic 11 (headless, xvfb+llvmpipe) → sabit kamera + uçan KIRMIZI rakip →
#   /camera/image → perception(source:=gazebo, backend:=mock renk-blob) → rakibi TESPİT eder.
# GPU GEREKMEZ (yazılım render). Amaç: render + kamera köprüsü + algı zincirini doğrulamak.
set -o pipefail
# NOT: TÜM source'lar set +u altında — ROS/Gazebo setup.sh dosyaları tanımsız değişken
# kullanır; set -u (nounset) aktifken script'i SESSİZCE çökertir (banner'dan önce).
set +u
source /opt/ros/humble/setup.bash
source /workspace/gokdogan-onboard/install/setup.bash 2>/dev/null || true
source /usr/share/gazebo/setup.sh 2>/dev/null || source /usr/share/gazebo-11/setup.sh 2>/dev/null || true
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export GAZEBO_MODEL_PATH=/workspace/sim/gazebo/models:/usr/share/gazebo-11/models:${GAZEBO_MODEL_PATH:-}
# gazebo_ros sistem eklentileri (libgazebo_ros_init/factory) ROS lib'inde → plugin path'e ekle
export GAZEBO_PLUGIN_PATH=/opt/ros/humble/lib:${GAZEBO_PLUGIN_PATH:-}
# headless yazılım GL (GPU'suz)
export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe QT_QPA_PLATFORM=offscreen

WORLD=/workspace/sim/gazebo/worlds/gokdogan_test.world
W=$(mktemp -d /tmp/gzsmoke.XXXXXX)

echo "=========================================================="
echo " GÖKDOĞAN — Gazebo Adım 1 (kamera-in-the-loop smoke)"
echo "=========================================================="
cleanup(){ pkill -f gzserver; pkill -f perception_node; pkill -f Xvfb; pkill -f "ros2 topic"; }
trap cleanup EXIT

echo "[1] gzserver (headless, xvfb + llvmpipe) — dünya yükleniyor"
# xvfb-run: sanal ekran sağlar → kamera sensörü GL context'i llvmpipe ile alır (GPU'suz)
xvfb-run -a -s "-screen 0 1280x1024x24" \
  gzserver --verbose -s libgazebo_ros_init.so -s libgazebo_ros_factory.so "$WORLD" \
  >"$W/gz.log" 2>&1 &
GZ=$!

# gazebo_ros_camera yayın topic'i: /<camera_name>/image_raw
CAM_TOPIC=/gokdogan_camera/image_raw
echo "[2] $CAM_TOPIC topic'i bekle (render + köprü çalışıyor mu)"
CAM=0
for i in $(seq 1 60); do
  ros2 topic list 2>/dev/null | grep -q "^${CAM_TOPIC}$" && { CAM=1; break; }
  sleep 1
done
[ "$CAM" = "1" ] || { echo "  ❌ $CAM_TOPIC gelmedi (render/köprü sorunu)"; tail -25 "$W/gz.log"; exit 1; }
echo "  ✅ $CAM_TOPIC yayınlanıyor"

echo "[3] kamera kare hızı (Hz) ölç (~4s)"
HZ=$(timeout 6 ros2 topic hz "$CAM_TOPIC" 2>/dev/null | grep -oE "average rate: [0-9.]+" | head -1)
echo "  ${HZ:-(hz ölçülemedi)}"

echo "[4] perception başlat (source=gazebo, backend=mock renk-blob; kamera topic remap)"
ros2 run gokdogan_perception perception_node --ros-args \
  -p source:=gazebo -p backend:=mock \
  -r /camera/image:="$CAM_TOPIC" >"$W/perc.log" 2>&1 &

echo "[5] rakip tespit ediliyor mu (/perception/detections, ~10s)"
DET=0
for i in $(seq 1 20); do
  N=$(timeout 3 ros2 topic echo --once /perception/detections gokdogan_msgs/msg/Detections 2>/dev/null | grep -cE "score:|track_id:|x:")
  if [ "${N:-0}" -gt 0 ]; then DET=1; echo "  ✅ tespit var (kırmızı rakip görüldü)"; break; fi
  sleep 1
done

echo "----------------------------------------------------------"
if [ "$CAM" = "1" ] && [ "$DET" = "1" ]; then
  echo " Gazebo Adım 1 GEÇTİ ✅  (headless render → kamera → algı → rakip tespiti)"
  exit 0
else
  echo " KISMİ ❌  cam=$CAM det=$DET"
  echo "--- gz.log (son 15) ---"; tail -15 "$W/gz.log"
  echo "--- perc.log (son 15) ---"; tail -15 "$W/perc.log"
  exit 1
fi
