#!/usr/bin/env python3
"""GÖKDOĞAN mock GCS — referans yer istasyonu (WPF'in yapacağını birebir taklit eder, SAD §9).

WPF MissionLinkClient (C#) davranışının Python referansı (Faz 9 sözleşmesi):
- TCP client → onboard:5006 (kontrol). exp-backoff reconnect.
- UDP :5005 bind → aircraft_vision alır (latest-wins).
- 1Hz heartbeat; operator_cmd / server_data / config gönderir.
- lock_valid / kamikaze_result / heartbeat alır.

Kullanım (test/CLI):
  python3 tools/mock_gcs.py --host 127.0.0.1 --duration 10 --start-lock-after 3 --server-data --summary
"""
import argparse
import json
import socket
import sys
import threading
import time

try:
    from gokdogan_mission_link import protocol as P
except ImportError:  # workspace source edilmemişse doğrudan yol ekle
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]
                          / "gokdogan-onboard/src/gokdogan_mission_link"))
    from gokdogan_mission_link import protocol as P


class MockGCS:
    def __init__(self, host, udp_port=P.UDP_PORT, tcp_port=P.TCP_PORT):
        self.host = host
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self._stop = threading.Event()
        self._tcp = None
        self._seq = 0
        self._lock = threading.Lock()
        # istatistikler (test doğrulaması için)
        self.stats = {
            "vision_count": 0, "last_fsm_state": None, "last_vision_seq": None,
            "vision_seq_gaps": 0, "lock_valid_count": 0, "kamikaze_count": 0,
            "hb_recv": 0, "tcp_connects": 0, "bad_frames": 0, "last_is_locked": None,
        }

    def _next(self):
        self._seq += 1
        return self._seq

    # ---- UDP: aircraft_vision al ----
    def _udp_loop(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", self.udp_port))
        s.settimeout(0.5)
        last_seq = None
        while not self._stop.is_set():
            try:
                data, _ = s.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = P.decode(data)
            except ValueError:
                self.stats["bad_frames"] += 1
                continue
            if not P.is_valid_envelope(msg) or msg.get("type") != "aircraft_vision":
                self.stats["bad_frames"] += 1
                continue
            self.stats["vision_count"] += 1
            self.stats["last_fsm_state"] = msg.get("fsm_state")
            self.stats["last_is_locked"] = msg.get("is_locked")
            seq = msg.get("seq")
            if last_seq is not None and seq > last_seq + 1:
                self.stats["vision_seq_gaps"] += (seq - last_seq - 1)
            last_seq = seq
            self.stats["last_vision_seq"] = seq
        s.close()

    # ---- TCP: kontrol kanalı (bağlan + al) ----
    def _tcp_loop(self):
        backoff = 0.5
        framer = P.TcpFramer(on_error=lambda m: self.stats.__setitem__(
            "bad_frames", self.stats["bad_frames"] + 1))
        while not self._stop.is_set():
            try:
                conn = socket.create_connection((self.host, self.tcp_port), timeout=2.0)
            except OSError:
                time.sleep(backoff)
                backoff = min(backoff * 2, 5.0)  # exp backoff
                continue
            backoff = 0.5
            conn.settimeout(0.5)
            with self._lock:
                self._tcp = conn
            self.stats["tcp_connects"] += 1
            while not self._stop.is_set():
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not data:
                    break
                for msg in framer.feed(data):
                    self._route(msg)
            with self._lock:
                self._tcp = None
            try:
                conn.close()
            except OSError:
                pass

    def _route(self, msg):
        t = msg.get("type")
        if t == "heartbeat":
            self.stats["hb_recv"] += 1
        elif t == "lock_valid":
            self.stats["lock_valid_count"] += 1
        elif t == "kamikaze_result":
            self.stats["kamikaze_count"] += 1

    def _send_tcp(self, msg):
        with self._lock:
            if self._tcp is None:
                return False
            try:
                self._tcp.sendall(P.frame_tcp(msg))
                return True
            except OSError:
                self._tcp = None
                return False

    # ---- gönderim yardımcıları (WPF komutları) ----
    def send_heartbeat(self):
        self._send_tcp(P.build("heartbeat", self._next(), role="gcs"))

    def send_operator_cmd(self, cmd, target_id=None, mode=None, params=None):
        self._send_tcp(P.build("operator_cmd", self._next(), cmd=cmd,
                               target_id=target_id, mode=mode, params=params))

    def send_server_data(self, opponents=None, hss=None, qr=None, server_time=None):
        self._send_tcp(P.build("server_data", self._next(),
                               opponents=opponents or [], hss=hss or [],
                               qr=qr, server_time=server_time or P.now_ts()))

    def send_config(self, weights):
        self._send_tcp(P.build("config", self._next(), autonomy_weights=weights))

    def start(self):
        threading.Thread(target=self._udp_loop, daemon=True).start()
        threading.Thread(target=self._tcp_loop, daemon=True).start()

    def stop(self):
        self._stop.set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--duration", type=float, default=10.0)
    ap.add_argument("--start-lock-after", type=float, default=None)
    ap.add_argument("--kamikaze-after", type=float, default=None)
    ap.add_argument("--server-data", action="store_true")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    gcs = MockGCS(args.host)
    gcs.start()
    t0 = time.time()
    lock_sent = False
    kami_sent = False
    next_hb = 0.0
    next_sd = 0.0
    while time.time() - t0 < args.duration:
        now = time.time() - t0
        if now >= next_hb:
            gcs.send_heartbeat()
            next_hb = now + 1.0
        if args.server_data and now >= next_sd:
            gcs.send_server_data(
                opponents=[{"takim_no": 42, "enlem": 39.9, "boylam": 32.8, "irtifa": 100.0,
                            "dikilme": 5.0, "yonelme": 270.0, "yatis": -3.0, "hiz": 25.0,
                            "zaman_farki": 0.2}],
                hss=[{"id": 1, "enlem": 39.91, "boylam": 32.81, "yaricap": 50.0}])
            next_sd = now + 1.0
        if args.start_lock_after is not None and not lock_sent and now >= args.start_lock_after:
            gcs.send_operator_cmd("START_LOCK")
            lock_sent = True
        if args.kamikaze_after is not None and not kami_sent and now >= args.kamikaze_after:
            gcs.send_operator_cmd("START_KAMIKAZE")
            kami_sent = True
        time.sleep(0.05)
    gcs.stop()
    time.sleep(0.3)
    if args.summary:
        print("MOCK_GCS_SUMMARY " + json.dumps(gcs.stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
