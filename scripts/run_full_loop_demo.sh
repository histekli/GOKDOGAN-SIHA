#!/usr/bin/env bash
# Kabul Kapısı 6 (Tam Döngü): mock_server + SITL + onboard + mock_gcs uçtan uca.
#   SITL→TAKEOFF→CRUISE → mock_gcs sunucuya ≤2Hz telemetri + ServerClock senkron + rakip/HSS relay
#   → /lock/event enjekte → lock_valid → GCS → mock_server kilitlenme POST.
#   + aralık-dışı telemetri sunucuca REDDEDİLİR (400/err3-4, ceza -0.2/sn önlenir).
#   + video_streamer: gi/GStreamer varsa STREAMING (RTSP), yoksa DEGRADED (çökmez).
set -o pipefail
set +u; source /opt/ros/humble/setup.bash
source /workspace/gokdogan-onboard/install/setup.bash
set -u
export ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
W=$(mktemp -d /tmp/fldemo.XXXXXX); cd "$W"
SRV_PORT=8081

echo "=========================================================="
echo " GÖKDOĞAN Kabul Kapısı 6 — Tam Döngü (mock_server + video)"
echo "=========================================================="
cleanup(){ pkill -f arducopter; pkill -f mavros_node; pkill -f mission; pkill -f aircraft_state;
           pkill -f video_streamer; pkill -f mock_server; pkill -f mock_gcs; pkill -f "ros2 launch"; }
trap cleanup EXIT

echo "[1] mock_server başlat (:$SRV_PORT)"
python3 /workspace/tools/mock_server.py --port $SRV_PORT --team 1 --duration 120 \
  >"$W/server.log" 2>&1 &
for i in $(seq 1 20); do grep -q "MOCK_SERVER listening" "$W/server.log" 2>/dev/null && break; sleep 0.5; done
grep -q "MOCK_SERVER listening" "$W/server.log" || { echo "  BAŞARISIZ: mock_server açılmadı"; cat "$W/server.log"; exit 1; }

echo "[2] SITL (ArduCopter, speedup 3)"
sim_vehicle.py -v ArduCopter -N -I0 --no-mavproxy --speedup 3 >"$W/sitl.log" 2>&1 &
for i in $(seq 1 40); do timeout 1 bash -c 'cat </dev/null >/dev/tcp/127.0.0.1/5760' 2>/dev/null && break; sleep 1; done

echo "[3] onboard graph (fsm + mission_link + aircraft_state + video; guidance/hss/kamikaze kapalı)"
ros2 launch gokdogan_bringup competition.launch.py mode:=sitl \
  enable_guidance:=false enable_hss:=false enable_kamikaze:=false enable_video:=true \
  >"$W/launch.log" 2>&1 &

state(){ timeout 3 ros2 topic echo --once --qos-durability transient_local /mission/mode 2>/dev/null | grep -oE "state: [0-9]+" | grep -oE "[0-9]+" | head -1; }
echo "[4] MAVROS connected bekle"
for i in $(seq 1 60); do timeout 3 ros2 topic echo --once /mavros/state 2>/dev/null | grep -q "connected: true" && break; sleep 1; done

echo "[5] mock_gcs başlat (sunucu döngüsü: login+saat+≤2Hz telemetri+relay, 40s)"
python3 /workspace/tools/mock_gcs.py --host 127.0.0.1 --duration 40 \
  --server-url "http://127.0.0.1:$SRV_PORT" --team 1 --summary \
  >"$W/gcs.log" 2>&1 &
GCS_PID=$!

echo "[6] TAKEOFF → CRUISE bekle"
ros2 service call /mission_fsm/set_mission_mode gokdogan_msgs/srv/SetMissionMode "{mode: 1}" >/dev/null 2>&1
CR=0
for i in $(seq 1 60); do S=$(state); [ "${S:-0}" = "2" ] && { CR=1; echo "  → CRUISE"; break; }; sleep 2; done
[ "$CR" = "1" ] || { echo "  BAŞARISIZ: CRUISE yok"; tail -15 "$W/launch.log"; exit 1; }

echo "[7] /lock/event enjekte (valid) → lock_valid → GCS → mock_server kilitlenme POST"
for k in 1 2 3; do
  ros2 topic pub --once /lock/event gokdogan_msgs/msg/LockEvent \
    "{valid: true, target_id: 42, box: {x: 960.0, y: 600.0, w: 120.0, h: 90.0}, center: [960.0, 600.0], progress_s: 4.0}" \
    >/dev/null 2>&1
  sleep 2
done

echo "[8] video_streamer durumu"
VST=$(timeout 3 ros2 topic echo --once --qos-durability transient_local /video/status 2>/dev/null | grep -oE "data: .*" | head -1)
echo "  ${VST:-video/status?}"

echo "[9] mock_gcs bitmesini bekle (2Hz telemetri akışı dursun)"
wait $GCS_PID 2>/dev/null
sleep 1

echo "[10] aralık-dışı telemetri (akış durdu → temiz governor) → REDDEDİLMELİ err4"
sleep 1   # sunucu governor min-aralığı dolsun ki reddin sebebi ARALIK olsun (rate değil)
python3 - "$SRV_PORT" >"$W/range.log" 2>&1 <<'PY'
import json, sys, urllib.request, urllib.error
port = sys.argv[1]
body = json.dumps({"iha_dikilme": 0.0, "iha_yonelme": 999.0, "iha_yatis": 0.0}).encode()
req = urllib.request.Request(f"http://127.0.0.1:{port}/api/telemetri_gonder", data=body,
                             headers={"Content-Type": "application/json"}, method="POST")
try:
    urllib.request.urlopen(req, timeout=2)
    print("RANGE_REJECT NO (kabul edildi — HATA)")
except urllib.error.HTTPError as e:
    obj = json.loads(e.read().decode())
    print(f"RANGE_REJECT YES status={e.code} hata_kodu={obj.get('hata_kodu')}")
PY
cat "$W/range.log"

echo "[11] sunucu istatistikleri (/api/_stats) + özetler"
SRV_SUM=$(python3 -c "import json,urllib.request as u; print(json.dumps(json.loads(u.urlopen('http://127.0.0.1:$SRV_PORT/api/_stats',timeout=2).read())))" 2>/dev/null)
pkill -f mock_server 2>/dev/null
sleep 1
GCS_SUM=$(grep "MOCK_GCS_SUMMARY" "$W/gcs.log" | tail -1 | sed 's/.*MOCK_GCS_SUMMARY //')
CLI_SUM=$(grep "GAME_SERVER_CLIENT_SUMMARY" "$W/gcs.log" | tail -1 | sed 's/.*GAME_SERVER_CLIENT_SUMMARY //')
echo "  GCS : ${GCS_SUM:-yok}"
echo "  CLI : ${CLI_SUM:-yok}"
echo "  SRV : ${SRV_SUM:-yok}"

echo "----------------------------------------------------------"
python3 - "$SRV_SUM" "$CLI_SUM" "$(echo "$VST")" "$(cat "$W/range.log")" <<'PY'
import json, sys
srv = json.loads(sys.argv[1]) if sys.argv[1] else {}
cli = json.loads(sys.argv[2]) if sys.argv[2] else {}
vst, rng = sys.argv[3], sys.argv[4]
ok = True
def check(name, cond):
    global ok
    print(f"  {'✅' if cond else '❌'} {name}")
    ok = ok and cond
check(f"telemetri sunucuya aktı (telemetry_ok={srv.get('telemetry_ok')})", srv.get("telemetry_ok", 0) >= 3)
check(f"governor ≤2Hz (rate_reject={srv.get('telemetry_rate_reject')}==0)", srv.get("telemetry_rate_reject", 1) == 0)
check(f"kilit POST'landı (lock_posts={srv.get('lock_posts')}≥1)", srv.get("lock_posts", 0) >= 1)
check(f"ServerClock senkron (clock_syncs={cli.get('clock_syncs')}≥1)", cli.get("clock_syncs", 0) >= 1)
check(f"QR/HSS relay GET (hss_gets={cli.get('hss_gets')}≥1)", cli.get("hss_gets", 0) >= 1)
check("aralık-dışı telemetri REDDEDİLDİ (400/err4)", "RANGE_REJECT YES" in rng and "hata_kodu=4" in rng)
# video: STREAMING (gi varsa) yeşil; DEGRADED sadece uyarı (gi yoksa; imaj rebuild gerekir)
if "STREAMING" in vst:
    check("video_streamer RTSP STREAMING", True)
elif "DEGRADED" in vst:
    print("  ⚠️  video_streamer DEGRADED (gi/GStreamer yok — imaj rebuild ile RTSP aktifleşir)")
else:
    check("video_streamer durumu yayınlandı", False)
print("----------------------------------------------------------")
if ok:
    print(" Kabul Kapısı 6 (Tam Döngü) GEÇTİ ✅")
    sys.exit(0)
print(" BAŞARISIZ ❌")
sys.exit(1)
PY
RC=$?
[ "$RC" = "0" ] || { echo "launch log kuyruğu:"; tail -12 "$W/launch.log"; }
exit $RC
