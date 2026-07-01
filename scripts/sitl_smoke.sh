#!/usr/bin/env bash
# Kabul Kapısı -1 (b): boş ArduCopter SITL aracını headless kaldır (GUIDED → arm → takeoff).
# Container içinde koşar. sim_vehicle.py'yi MAVProxy'siz başlatır; araç MAVLink'i tcp:5760'ta sunar.
set -uo pipefail
source /opt/ros/humble/setup.bash

AP="${ARDUPILOT_HOME:-/opt/ardupilot}"
WORK="$(mktemp -d /tmp/sitl.XXXXXX)"
cd "$WORK"

echo "=========================================================="
echo " GÖKDOĞAN Kabul Kapısı -1 (b) — SITL takeoff"
echo " çalışma dizini: $WORK"
echo "=========================================================="

# ArduCopter SITL, MAVProxy olmadan → MAVLink yalnız tcp:5760'ta (pymavlink doğrudan bağlanır).
sim_vehicle.py -v ArduCopter -N -I0 --no-mavproxy \
    --speedup 5 > "$WORK/sitl.log" 2>&1 &
SITL_PID=$!
cleanup() { kill "$SITL_PID" 2>/dev/null; pkill -f arducopter 2>/dev/null; }
trap cleanup EXIT

echo "[sitl] başlatıldı (pid=$SITL_PID), tcp:5760 bekleniyor..."
OPEN=0
for i in $(seq 1 60); do
  if timeout 1 bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/5760' 2>/dev/null; then
    OPEN=1; echo "[sitl] tcp:5760 açık ($i s)"; break
  fi
  if ! kill -0 "$SITL_PID" 2>/dev/null; then
    echo "[sitl] HATA: SITL süreci öldü. Log:"; tail -30 "$WORK/sitl.log"; exit 1
  fi
  sleep 1
done
if [ "$OPEN" -ne 1 ]; then
  echo "[sitl] HATA: tcp:5760 açılmadı. Log:"; tail -40 "$WORK/sitl.log"; exit 1
fi

SITL_CONN="tcp:127.0.0.1:5760" SMOKE_ALT="${SMOKE_ALT:-10}" python3 /workspace/scripts/smoke_takeoff.py
RC=$?

echo "----------------------------------------------------------"
if [ $RC -eq 0 ]; then
  echo " Kabul Kapısı -1 (b) GEÇTİ ✅  (SITL kalkış doğrulandı)"
else
  echo " Kabul Kapısı -1 (b) BAŞARISIZ ❌  (RC=$RC). Son SITL log:"
  tail -30 "$WORK/sitl.log"
fi
echo "=========================================================="
exit $RC
