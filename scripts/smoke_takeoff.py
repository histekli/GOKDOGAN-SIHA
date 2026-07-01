#!/usr/bin/env python3
"""Kabul Kapısı -1 (b) — boş SITL aracı GUIDED → arm → takeoff doğrulaması.

pymavlink ile SITL MAVLink uç noktasına bağlanır; GUIDED moda geçer, arm eder,
NAV_TAKEOFF verir ve aracın hedef irtifaya çıktığını (relative_alt) doğrular.
Çıkış kodu 0 = geçti. Bu, toolchain'in (ROS2 Humble değil, ArduPilot SITL) uçtan
uca çalıştığını kanıtlar — Faz 1'de yerini MAVROS entegrasyon testine bırakır.
"""
import os
import sys
import time

from pymavlink import mavutil

CONN = os.environ.get("SITL_CONN", "tcp:127.0.0.1:5760")
TARGET_ALT = float(os.environ.get("SMOKE_ALT", "10.0"))
CONNECT_TIMEOUT = 60
ARM_TIMEOUT = 60
TAKEOFF_TIMEOUT = 90


def log(msg):
    print(f"[smoke] {msg}", flush=True)


def main():
    log(f"Bağlanılıyor: {CONN}")
    m = mavutil.mavlink_connection(CONN, retries=CONNECT_TIMEOUT)
    m.wait_heartbeat(timeout=CONNECT_TIMEOUT)
    log(f"Heartbeat alındı (sys={m.target_system} comp={m.target_component})")

    # Telemetri akışını iste
    m.mav.request_data_stream_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1,
    )

    # EKF/GPS ve armable olana kadar bekle (prearm)
    log("Prearm/EKF bekleniyor...")
    deadline = time.time() + ARM_TIMEOUT
    while time.time() < deadline:
        m.recv_match(type=["SYS_STATUS", "EKF_STATUS_REPORT", "GPS_RAW_INT"],
                     blocking=True, timeout=2)
        # GUIDED moda geçmeyi dene (armable ise tutar)
        set_mode(m, "GUIDED")
        if try_arm(m):
            break
    else:
        log("HATA: araç arm edilemedi (prearm/EKF timeout)")
        return 1
    log("Araç ARMED")

    # Takeoff
    log(f"NAV_TAKEOFF → {TARGET_ALT} m")
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0,
        0, 0, 0, 0, 0, 0, TARGET_ALT,
    )

    deadline = time.time() + TAKEOFF_TIMEOUT
    reached = 0.0
    while time.time() < deadline:
        msg = m.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=2)
        if not msg:
            continue
        rel = msg.relative_alt / 1000.0
        reached = max(reached, rel)
        log(f"  relative_alt = {rel:6.2f} m")
        if rel >= TARGET_ALT * 0.9:
            log(f"BAŞARILI ✅ hedef irtifaya ulaşıldı ({rel:.2f} m ≥ {TARGET_ALT*0.9:.2f} m)")
            return 0

    log(f"HATA: takeoff timeout — en yüksek irtifa {reached:.2f} m (< {TARGET_ALT*0.9:.2f} m)")
    return 1


def set_mode(m, mode_name):
    mode_id = m.mode_mapping().get(mode_name)
    if mode_id is None:
        return
    m.mav.set_mode_send(
        m.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
    )


def try_arm(m):
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
        1, 0, 0, 0, 0, 0, 0,
    )
    ack = m.recv_match(type="COMMAND_ACK", blocking=True, timeout=3)
    if ack and ack.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
        return ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED
    # ACK gelmezse HEARTBEAT armed bayrağına bak
    hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
    if hb:
        return bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
    return False


if __name__ == "__main__":
    sys.exit(main())
