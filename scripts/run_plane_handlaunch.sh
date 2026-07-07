#!/usr/bin/env bash
# Sabit-kanat ELLE FIRLATMA demosu — X-UAV Mini Talon (gokdogan_talon).
#   Gazebo (DISPLAY varsa GUI, yoksa headless) + ArduPlane SITL + arm + fırlatma + telemetri.
#   GUI ile izlemek:  GZ_HW=1 make run-plane-handlaunch     (GZ_HW=1 = host GPU, şart!)
#   Fırlatma ayarı:   TOSS_VX/TOSS_VY/TOSS_VZ (varsayılan 20/0/8; Talon +x ileri)
set +u
source /opt/ros/humble/setup.bash
source /workspace/gokdogan-onboard/install/setup.bash 2>/dev/null
source /usr/share/gazebo/setup.sh 2>/dev/null || source /usr/share/gazebo-11/setup.sh 2>/dev/null
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export GAZEBO_PLUGIN_PATH=/workspace/sim/gazebo/ardupilot_gazebo/build:/opt/ros/humble/lib
export GAZEBO_MODEL_PATH=/workspace/sim/gazebo/models:/workspace/sim/gazebo/ardupilot_gazebo/models:/usr/share/gazebo-11/models
export GAZEBO_MODEL_DATABASE_URI=""
WORLD="${WORLD:-/workspace/sim/gazebo/worlds/talon_test.world}"
ENTITY=gokdogan_talon
TVX="${TOSS_VX:-20}"; TVY="${TOSS_VY:-0}"; TVZ="${TOSS_VZ:-8}"

# Artık-koruması: eski bir koşu (asılı konteyner) SITL portunu tutuyorsa her şey sessizce bozulur
if timeout 1 bash -c 'cat </dev/null >/dev/tcp/127.0.0.1/5760' 2>/dev/null; then
  echo "HATA: 5760 portu zaten dolu — eski bir koşunun artığı çalışıyor."
  echo "      Host'ta:  docker ps   →   docker kill <ID>   (gokdogan-dev konteynerlerini kapat), sonra tekrar dene."
  exit 1
fi

if [ -n "${DISPLAY:-}" ] && [ -e /tmp/.X11-unix ]; then
  unset QT_QPA_PLATFORM
  if [ "${GZ_HW:-0}" = "1" ]; then
    # imaj ENV'i LIBGL_ALWAYS_SOFTWARE=1 gömer — unset edilmezse GPU verilse bile yazılım render kalır
    unset LIBGL_ALWAYS_SOFTWARE GALLIUM_DRIVER
    [ -e /dev/dri ] || echo "UYARI: GZ_HW=1 ama konteynerde /dev/dri yok → yine yazılım render! (Makefile'daki GPU_DEV satırı güncel mi?)"
  else
    export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe
    echo "UYARI: GUI yazılım render (llvmpipe) ile açılıyor — ÇOK YAVAŞ olabilir."
    echo "       Hızlı GUI için:  GZ_HW=1 make run-plane-handlaunch"
  fi
  echo "[GUI] Gazebo penceresi açılıyor — uçağın davranışını izle"
  echo "      Uçağın KAMERASI: başka terminalde  make shell  →  rqt_image_view /gokdogan_camera/image_raw"
  gazebo --verbose -s libgazebo_ros_init.so -s libgazebo_ros_force_system.so "$WORLD" >/workspace/_hl_gz.log 2>&1 &
else
  export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe QT_QPA_PLATFORM=offscreen
  echo "[HEADLESS] xvfb + llvmpipe"
  xvfb-run -a gzserver -s libgazebo_ros_init.so -s libgazebo_ros_force_system.so "$WORLD" >/workspace/_hl_gz.log 2>&1 &
fi
cleanup(){ pkill -f gzserver; pkill -f gazebo; pkill -f arduplane; pkill -f sim_vehicle; pkill Xvfb; }
trap cleanup EXIT

echo "[1/4] dünya yükleniyor..."
for i in $(seq 1 90); do
  timeout 2 bash -c 'gz topic -l' 2>/dev/null | grep -q pose && { echo "      dünya hazır (${i}s)"; break; }
  [ $((i % 5)) -eq 0 ] && echo "      ... ${i}s (GUI'de ilk açılış 1-2 dk sürebilir)"
  sleep 1
done

# GUI penceresinin ekrana gelmesi sunucudan yavaştır — uçuşu kaçırmamak için izleme payı
if [ -n "${DISPLAY:-}" ] && [ -e /tmp/.X11-unix ]; then
  W="${WATCH_DELAY:-15}"
  [ "$W" -gt 0 ] && { echo "      GUI penceresi için ${W}s izleme payı (WATCH_DELAY ile ayarla)..."; sleep "$W"; }
fi

echo "[2/4] ArduPlane SITL başlıyor..."
sim_vehicle.py -v ArduPlane -f gazebo-zephyr -N -I0 --no-mavproxy --speedup 1 \
  --add-param-file=/workspace/sim/gazebo/config/mini_talon_vtail.param \
  --add-param-file=/workspace/sim/gazebo/config/gazebo_sitl.param >/workspace/_hl_sitl.log 2>&1 &
for i in $(seq 1 60); do
  timeout 1 bash -c 'cat </dev/null >/dev/tcp/127.0.0.1/5760' 2>/dev/null && { echo "      SITL hazır (${i}s)"; break; }
  [ $((i % 5)) -eq 0 ] && echo "      ... SITL bekleniyor ${i}s"
  sleep 1
  if [ "$i" = "60" ]; then
    echo "HATA: SITL 60s içinde açılmadı. Log kuyruğu:"; tail -8 /workspace/_hl_sitl.log; exit 1
  fi
done

echo "[3/4] arm (TAKEOFF modu) + fırlatma ($TVX,$TVY,$TVZ)"
export ENTITY
python3 - "$TVX" "$TVY" "$TVZ" <<'PY'
import sys, time, os, rclpy
from gazebo_msgs.srv import ApplyLinkWrench
from builtin_interfaces.msg import Duration
from pymavlink import mavutil
vx,vy,vz=map(float,sys.argv[1:4])
link=os.environ.get('ENTITY','gokdogan_talon')+'::base_link'
rclpy.init(); n=rclpy.create_node('hl')
c=n.create_client(ApplyLinkWrench,'/apply_link_wrench'); c.wait_for_service(timeout_sec=20)
m=mavutil.mavlink_connection('tcp:127.0.0.1:5760'); m.wait_heartbeat(timeout=40); print("      HEARTBEAT ok",flush=True)
m.mav.request_data_stream_send(m.target_system,m.target_component,mavutil.mavlink.MAV_DATA_STREAM_ALL,5,1)
def sp(k,v,t=9): m.mav.param_set_send(m.target_system,m.target_component,k.encode(),float(v),t)
sp('TKOFF_THR_MINACC',0); sp('TKOFF_THR_MINSPD',0); sp('TKOFF_ALT',60); time.sleep(3)
# EKF oturana kadar TAKEOFF modu reddedilebilir (MANUAL'de kalır) — kabul edilene dek dene
for i in range(40):
    m.set_mode('TAKEOFF')
    hb=m.recv_match(type='HEARTBEAT',blocking=True,timeout=2)
    if hb and mavutil.mode_string_v10(hb)=='TAKEOFF':
        print(f"      mod=TAKEOFF ({i+1}. denemede)",flush=True); break
    time.sleep(1)
else:
    print("      UYARI: TAKEOFF modu kabul edilmedi (EKF/GPS?) — MANUAL ile devam",flush=True)
armed=False
for i in range(15):
    m.mav.command_long_send(m.target_system,m.target_component,mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,0,1,0,0,0,0,0,0)
    hb=m.recv_match(type='HEARTBEAT',blocking=True,timeout=2)
    if hb and hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
        armed=True; print(f"      ARMED mode={mavutil.mode_string_v10(hb)}",flush=True); break
    time.sleep(1)
if not armed: print("      ARM OLMADI — /workspace/_hl_sitl.log içindeki PreArm satırlarına bak",flush=True)
time.sleep(3)  # gaz spool (ArduPlane TAKEOFF modu motoru yükseltir); fırlatma bunun ivmesini kullanır
r=ApplyLinkWrench.Request(); r.link_name=link; r.reference_frame='world'
r.wrench.force.x=vx*2.2; r.wrench.force.y=vy*2.2; r.wrench.force.z=abs(vz)*2.2+22.0
r.duration=Duration(sec=0,nanosec=800000000)
f=c.call_async(r); rclpy.spin_until_future_complete(n,f,timeout_sec=3)
print(f"      TOSS(wrench) ok={f.result().success if f.result() else 'SERVIS_CEVAPSIZ'}",flush=True)
print("[4/4] uçuş telemetrisi (40s):",flush=True)
mx=0; t0=time.time(); last=0
while time.time()-t0<40:
    g=m.recv_match(type='GLOBAL_POSITION_INT',blocking=True,timeout=1)
    v=m.recv_match(type='VFR_HUD',blocking=False)
    at=m.recv_match(type='ATTITUDE',blocking=False)
    if g:
        a=g.relative_alt/1000.0; mx=max(mx,a)
        if time.time()-last>=1.0:
            last=time.time()
            ex=f" aspd={v.airspeed:.1f} gspd={v.groundspeed:.1f} thr={v.throttle}%" if v else ""
            ex+=f" pitch={at.pitch*57.3:.0f}° roll={at.roll*57.3:.0f}°" if at else ""
            print(f"  rel_alt={a:.1f}m (max {mx:.1f}){ex}",flush=True)
print(("UCUYOR ✅" if mx>15 else f"surduremedi (max {mx:.1f}m) — TOSS_VX/VZ dene, uçuş tuning devam ediyor"),flush=True)
PY
echo "bitti (Ctrl+C ile kapat)"
sleep 3
echo "--- TANI: SITL log kuyruğu ---"; tail -5 /workspace/_hl_sitl.log 2>/dev/null
echo "--- TANI: gazebo hataları ---"; grep -iE "error|unable|invalid" /workspace/_hl_gz.log 2>/dev/null | grep -ivE "audio|OpenAL|ALSA" | head -3
