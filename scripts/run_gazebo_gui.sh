#!/usr/bin/env bash
# Gazebo'yu GÖRSEL aç (host X11) — simülasyonu GÖZÜNLE izle.
# `make gazebo-gui` ile çağrılır (xhost + X11 socket mount Makefile'da yapılır).
# Rakip kırmızı uçak x=45'te süzülür; QR 2x2m plakası sol-altta 45° eğik durur.
set +u
source /opt/ros/humble/setup.bash
source /workspace/gokdogan-onboard/install/setup.bash 2>/dev/null || true
source /usr/share/gazebo/setup.sh 2>/dev/null || source /usr/share/gazebo-11/setup.sh 2>/dev/null || true
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export GAZEBO_MODEL_PATH=/workspace/sim/gazebo/models:/workspace/sim/gazebo/ardupilot_gazebo/models:/usr/share/gazebo-11/models
export GAZEBO_PLUGIN_PATH=/workspace/sim/gazebo/ardupilot_gazebo/build:/opt/ros/humble/lib
export GAZEBO_MODEL_DATABASE_URI=""   # ölü online DB'yi kapat (ArduPilotPlugin yüklensin)
WORLD="${WORLD:-/workspace/sim/gazebo/worlds/gokdogan_test.world}"   # WORLD=.../talon_test.world ile Talon

# ÖNEMLİ: imaj ENV'inde QT_QPA_PLATFORM=offscreen var (headless için) → GUI'yi engeller. Kaldır.
unset QT_QPA_PLATFORM

# GPU passthrough yoksa yazılım render (yavaş ama GÖRÜNÜR). Donanımlı denemek için: GZ_HW=1 make gazebo-gui
if [ "${GZ_HW:-0}" != "1" ]; then
  export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe
  echo "[render] yazılım GL (llvmpipe) — yavaş ama görünür. Hızlı istersen: GZ_HW=1 make gazebo-gui"
fi

if ! xset q >/dev/null 2>&1; then
  echo "⚠️  X ekranına erişilemiyor (DISPLAY=$DISPLAY). Host'ta 'xhost +local:docker' çalıştır."
fi

echo "Gazebo GUI açılıyor: $WORLD  (kapatmak için pencereyi kapat / Ctrl+C)"
echo "  • Perception dünyası: kırmızı rakip + QR yer-hedefi"
echo "  • Talon dünyası (WORLD=.../talon_test.world): kameralı sabit-kanat uçağımız"
echo "  • Kamera: ikinci terminalde  make shell → rqt_image_view /gokdogan_camera/image_raw"
exec gazebo --verbose "$WORLD"
