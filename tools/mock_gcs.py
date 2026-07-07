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
import urllib.error
import urllib.request

try:
    from gokdogan_mission_link import protocol as P
except ImportError:  # workspace source edilmemişse doğrudan yol ekle
    import pathlib

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "gokdogan-onboard/src/gokdogan_mission_link"))
    from gokdogan_mission_link import protocol as P


# =========================================================================== #
#  Sunucu (HTTP) tarafı — WPF GameServerClient'ın Python referansı (SAD §15).  #
#  Gerçek yarışmada C# HttpClient; burada dev/entegrasyon testi için urllib.   #
# =========================================================================== #

# KTR telemetri aralıkları (mock_server ile birebir): aralık-dışı → clamp (paket reddini önle).
RANGE_DIKILME = (-90.0, 90.0)
RANGE_YONELME = (0.0, 360.0)
RANGE_YATIS = (-90.0, 90.0)


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class ServerClock:
    """1Hz midpoint round-trip ile sunucu saati offset'i (SAD §15).

    offset = t_server − (t_send+t_recv)/2. En düşük RTT'li örnek seçilir (en doğru);
    üretilen saat **monotonik** (asla geri gitmez).
    """

    def __init__(self):
        self._offset = 0.0
        self._best_rtt = None
        self._last_emit = None
        self._synced = False

    def update(self, t_send, t_server, t_recv):
        rtt = max(0.0, t_recv - t_send)
        off = t_server - (t_send + t_recv) / 2.0
        if self._best_rtt is None or rtt <= self._best_rtt:
            self._best_rtt = rtt
            self._offset = off
            self._synced = True
        return self._offset

    @property
    def synced(self):
        return self._synced

    @property
    def offset(self):
        return self._offset

    def now(self):
        t = time.time() + self._offset
        if self._last_emit is not None and t < self._last_emit:
            t = self._last_emit  # monotonik garanti
        self._last_emit = t
        return t


class TelemetryHzMeter:
    """≤2Hz governor (SAD §15): 5s kayan pencere + min-aralık. >2Hz'i gönderim ÖNCESİ engeller."""

    def __init__(self, max_hz=2.0, window_s=5.0):
        self.max_hz = max_hz
        self.window_s = window_s
        self._min_gap = 1.0 / max_hz
        self._sends = []

    def allow(self, now=None):
        now = time.time() if now is None else now
        # pencere dışını at
        cutoff = now - self.window_s
        self._sends = [t for t in self._sends if t >= cutoff]
        if self._sends and (now - self._sends[-1]) < self._min_gap:
            return False
        if len(self._sends) >= self.max_hz * self.window_s:
            return False
        return True

    def record(self, now=None):
        self._sends.append(time.time() if now is None else now)


class GameServerClient:
    """WPF GameServerClient referansı: login, ServerClock, ≤2Hz telemetri (aralık clamp),
    kilit/kamikaze POST, QR/HSS GET. 401→re-login, 5xx→backoff retry (SAD §15)."""

    def __init__(self, base_url, team=1, password="gokdogan", timeout=2.0):
        self.base = base_url.rstrip("/")
        self.team = team
        self.password = password
        self.timeout = timeout
        self.token = None
        self.clock = ServerClock()
        self.meter = TelemetryHzMeter(max_hz=2.0)
        self.stats = {
            "login_ok": 0,
            "telemetry_sent": 0,
            "telemetry_governed": 0,
            "telemetry_clamped": 0,
            "lock_posts": 0,
            "kamikaze_posts": 0,
            "qr_gets": 0,
            "hss_gets": 0,
            "clock_syncs": 0,
            "http_errors": 0,
            "relogins": 0,
        }
        self.last_opponents = []
        self.last_hss = []
        self.last_qr = None

    # ---- düşük seviye HTTP (retry/backoff, 401→re-login) ----
    def _request(self, method, path, body=None, _relogin=True):
        url = self.base + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        backoff = 0.2
        for attempt in range(3):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.status, json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                payload = {}
                try:
                    payload = json.loads(e.read().decode("utf-8"))
                except Exception:  # noqa: BLE001
                    pass
                if e.code == 401 and _relogin and self.login():
                    self.stats["relogins"] += 1
                    return self._request(method, path, body, _relogin=False)
                if 500 <= e.code < 600:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 1.0)
                    continue
                self.stats["http_errors"] += 1
                return e.code, payload  # 400 vb. → çağıran KTR hata_kodu'nu görür
            except (urllib.error.URLError, OSError, ValueError):
                self.stats["http_errors"] += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 1.0)
        return None, None

    def login(self):
        status, obj = self._request(
            "POST", "/api/giris", {"takim_numarasi": self.team, "sifre": self.password}, _relogin=False
        )
        if status == 200 and obj and obj.get("token"):
            self.token = obj["token"]
            self.stats["login_ok"] += 1
            return True
        return False

    def sync_clock(self):
        t_send = time.time()
        status, obj = self._request("GET", "/api/sunucusaati")
        t_recv = time.time()
        if status == 200 and obj and "epoch" in obj:
            self.clock.update(t_send, obj["epoch"], t_recv)
            self.stats["clock_syncs"] += 1
            return True
        return False

    def build_telemetry(self, flight, vision):
        """FlightState + vision (bbox/flag mission_link'ten) → KTR telemetri paketi.

        Aralık-dışı açılar CLAMP edilir (tüm paket reddini/−0.2 cezasını önler, SAD §15).
        """
        pkt = dict(flight)
        for name, (lo, hi) in (
            ("iha_dikilme", RANGE_DIKILME),
            ("iha_yonelme", RANGE_YONELME),
            ("iha_yatis", RANGE_YATIS),
        ):
            if name in pkt:
                c = _clamp(float(pkt[name]), lo, hi)
                if c != pkt[name]:
                    self.stats["telemetry_clamped"] += 1
                pkt[name] = c
        pkt["takim_numarasi"] = self.team
        if vision:
            pkt["hedef_merkez_X"] = vision.get("target_center_x")
            pkt["hedef_merkez_Y"] = vision.get("target_center_y")
            pkt["hedef_genislik"] = vision.get("target_width")
            pkt["hedef_yukseklik"] = vision.get("target_height")
            pkt["iha_kilitlenme"] = 1 if vision.get("is_locked") else 0
            pkt["iha_otonom"] = 1 if vision.get("fsm_state", 0) not in (0, 7) else 0
        pkt["gps_saati"] = self.clock.now()
        return pkt

    def send_telemetry(self, flight, vision=None, now=None):
        """Governor ≤2Hz: izin varsa gönder. (True=gönderildi, False=engellendi/hata)."""
        if not self.meter.allow(now):
            self.stats["telemetry_governed"] += 1
            return False
        pkt = self.build_telemetry(flight, vision)
        status, obj = self._request("POST", "/api/telemetri_gonder", pkt)
        if status == 200:
            self.meter.record(now)
            self.stats["telemetry_sent"] += 1
            if obj and "konumBilgileri" in obj:
                self.last_opponents = obj["konumBilgileri"]
            return True
        return False

    def post_lock(self, event):
        status, _ = self._request(
            "POST",
            "/api/kilitlenme_bilgisi",
            {
                "kilitlenmeBaslangicZamani": self.clock.now(),
                "kilitlenmeBitisZamani": event.get("lock_end_ts", self.clock.now()),
                "otonom_kilitlenme": 1,
                "hedef_id": event.get("target_id"),
            },
        )
        if status == 200:
            self.stats["lock_posts"] += 1
            return True
        return False

    def post_kamikaze(self, event):
        status, _ = self._request(
            "POST",
            "/api/kamikaze_bilgisi",
            {
                "kamikazeZamani": self.clock.now(),
                "basarili": 1 if event.get("success") else 0,
                "qr_metni": event.get("qr_text", ""),
            },
        )
        if status == 200:
            self.stats["kamikaze_posts"] += 1
            return True
        return False

    def get_qr(self):
        status, obj = self._request("GET", "/api/qr_koordinati")
        if status == 200 and obj:
            self.last_qr = obj
            self.stats["qr_gets"] += 1
            return obj
        return None

    def get_hss(self):
        status, obj = self._request("GET", "/api/hss_koordinatlari")
        if status == 200 and obj:
            self.last_hss = obj.get("hss_koordinat_bilgileri", [])
            self.stats["hss_gets"] += 1
            return self.last_hss
        return None


class MockGCS:
    def __init__(self, host, udp_port=P.UDP_PORT, tcp_port=P.TCP_PORT):
        self.host = host
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self._stop = threading.Event()
        self._tcp = None
        self._seq = 0
        self._lock = threading.Lock()
        self.server = None  # opsiyonel GameServerClient (kilit/kamikaze relay)
        self.last_vision = None  # son aircraft_vision (telemetri paketi kurulumu için)
        # istatistikler (test doğrulaması için)
        self.stats = {
            "vision_count": 0,
            "last_fsm_state": None,
            "last_vision_seq": None,
            "vision_seq_gaps": 0,
            "lock_valid_count": 0,
            "kamikaze_count": 0,
            "hb_recv": 0,
            "tcp_connects": 0,
            "bad_frames": 0,
            "last_is_locked": None,
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
            self.last_vision = msg
            seq = msg.get("seq")
            if last_seq is not None and seq > last_seq + 1:
                self.stats["vision_seq_gaps"] += seq - last_seq - 1
            last_seq = seq
            self.stats["last_vision_seq"] = seq
        s.close()

    # ---- TCP: kontrol kanalı (bağlan + al) ----
    def _tcp_loop(self):
        backoff = 0.5
        framer = P.TcpFramer(on_error=lambda m: self.stats.__setitem__("bad_frames", self.stats["bad_frames"] + 1))
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
            if self.server is not None and msg.get("valid"):
                self.server.post_lock(msg)  # onboard olayı → sunucu POST (≤2s, SAD §15)
        elif t == "kamikaze_result":
            self.stats["kamikaze_count"] += 1
            if self.server is not None:
                self.server.post_kamikaze(msg)

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
        self._send_tcp(P.build("operator_cmd", self._next(), cmd=cmd, target_id=target_id, mode=mode, params=params))

    def send_server_data(self, opponents=None, hss=None, qr=None, server_time=None):
        self._send_tcp(
            P.build(
                "server_data",
                self._next(),
                opponents=opponents or [],
                hss=hss or [],
                qr=qr,
                server_time=server_time or P.now_ts(),
            )
        )

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
    ap.add_argument(
        "--server-data", action="store_true", help="sabit sentetik rakip/HSS'i onboard'a yolla (sunucu yoksa)"
    )
    ap.add_argument(
        "--server-url", default=None, help="mock_server URL'i (örn http://127.0.0.1:8081) — tam döngü relay"
    )
    ap.add_argument("--team", type=int, default=1)
    ap.add_argument("--password", default="gokdogan")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    gcs = MockGCS(args.host)
    gcs.start()

    server = None
    if args.server_url:
        server = GameServerClient(args.server_url, team=args.team, password=args.password)
        server.login()
        gcs.server = server  # kilit/kamikaze olaylarını sunucuya POST'lasın

    t0 = time.time()
    lock_sent = False
    kami_sent = False
    next_hb = 0.0
    next_sd = 0.0
    next_srv = 0.0  # sunucu döngüsü (saat/telemetri/relay) ~2Hz
    while time.time() - t0 < args.duration:
        now = time.time() - t0
        if now >= next_hb:
            gcs.send_heartbeat()
            next_hb = now + 1.0
        if server is not None and now >= next_srv:
            server.sync_clock()
            # telemetri: ArduPilot flight state gerçek GCS'te MAVLink'ten; mock'ta makul sentetik
            flight = {
                "iha_enlem": 39.90,
                "iha_boylam": 32.80,
                "iha_irtifa": 100.0,
                "iha_dikilme": 3.0,
                "iha_yonelme": 270.0,
                "iha_yatis": -2.0,
                "iha_hiz": 20.0,
                "iha_batarya": 85,
            }
            server.send_telemetry(flight, gcs.last_vision)  # governor ≤2Hz içeride
            opp = server.last_opponents
            hss = server.get_hss() or []
            # KTR alan adları → dondurulmuş mission_link şeması (opponent/hss $defs)
            gcs.send_server_data(
                opponents=[
                    {
                        "takim_no": o.get("takim_numarasi", 0),
                        "enlem": o.get("iha_enlem"),
                        "boylam": o.get("iha_boylam"),
                        "irtifa": o.get("iha_irtifa", 0.0),
                        "hiz": o.get("iha_hizi", 0.0),  # CEVAP alanı iha_hizi (Haberleşme §7.3)
                        "yonelme": o.get("iha_yonelme", 0.0),
                        "zaman_farki": o.get("zaman_farki", 0.0),
                    }
                    for o in opp
                ],
                hss=[
                    {
                        "id": h.get("id"),
                        "enlem": h.get("hssEnlem"),
                        "boylam": h.get("hssBoylam"),
                        "yaricap": h.get("hssYaricap", 0.0),
                    }
                    for h in hss
                ],
                server_time=server.clock.now(),
            )
            next_srv = now + 0.5
        elif args.server_data and now >= next_sd:
            gcs.send_server_data(
                opponents=[
                    {
                        "takim_no": 42,
                        "enlem": 39.9,
                        "boylam": 32.8,
                        "irtifa": 100.0,
                        "dikilme": 5.0,
                        "yonelme": 270.0,
                        "yatis": -3.0,
                        "hiz": 25.0,
                        "zaman_farki": 0.2,
                    }
                ],
                hss=[{"id": 1, "enlem": 39.91, "boylam": 32.81, "yaricap": 50.0}],
            )
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
        if server is not None:
            print("GAME_SERVER_CLIENT_SUMMARY " + json.dumps(server.stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
