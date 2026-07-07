#!/usr/bin/env python3
"""GÖKDOĞAN mock_server — yarışma (KTR Savaşan İHA) sunucu API'sinin DEV emülatörü.

Amaç (SAD §15, prompt Faz 6): C# `GameServerClient` + onboard'ı **donanımsız** uçtan uca test
etmek. Gerçek yarışma sunucusunun sözleşmesini birebir taklit eder ki GCS'in doğru davrandığı
(≤2Hz governor, aralık doğrulama, ServerClock) mock ile doğrulanabilsin.

Endpoint'ler (KTR 6.2/6.4):
  POST /api/giris                → oturum (takım no + şifre) → token
  GET  /api/sunucusaati          → sunucu saati (ServerClock midpoint kaynağı)
  POST /api/telemetri_gonder     → telemetri (≤2Hz zorunlu; >2Hz → 400 / hata 3;
                                   aralık-dışı dikilme/yonelme/yatis → 400 / hata 4)
  POST /api/kilitlenme_bilgisi   → kilit olayı
  POST /api/kamikaze_bilgisi     → kamikaze olayı
  GET  /api/qr_koordinati        → QR hedef koordinatı (sentetik)
  GET  /api/hss_koordinatlari    → aktif HSS bölgeleri (sentetik)

Tasarım: HTTP I/O'dan bağımsız **saf `ServerCore`** (governor + aralık doğrulama + sentetik
veri) birim-test edilir; `MockServerHandler` yalnız stdlib `http.server` sarmalayıcısıdır
(harici bağımlılık YOK).

Kullanım:
  python3 tools/mock_server.py --host 127.0.0.1 --port 8081 [--seed 0]
"""

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# KTR telemetri aralıkları (SAD §15, şartname): aralık-dışı → paket reddi (ceza -0.2/sn önlenir)
RANGE_DIKILME = (-90.0, 90.0)  # pitch
RANGE_YONELME = (0.0, 360.0)  # heading/yaw
RANGE_YATIS = (-90.0, 90.0)  # roll

# Governor: KTR telemetriyi ≤2Hz kabul eder; üstü ceza. Min aralık 0.5s − küçük tolerans.
MIN_TELEMETRY_PERIOD_S = 0.5
TELEMETRY_PERIOD_TOL_S = 0.02  # zamanlayıcı jitter'ına küçük pay (0.48s hâlâ geçerli)

# Hata kodları (KTR benzeri; GCS bunları görüp davranışını doğrular)
ERR_BAD_SESSION = 1
ERR_BAD_FIELDS = 2
ERR_RATE_LIMIT = 3  # >2Hz telemetri
ERR_OUT_OF_RANGE = 4  # dikilme/yonelme/yatis aralık dışı


class ApiError(Exception):
    """HTTP durum + KTR hata kodu taşıyan uygulama hatası."""

    def __init__(self, status, err_code, message):
        super().__init__(message)
        self.status = status
        self.err_code = err_code
        self.message = message


def _in_range(value, lo, hi):
    return isinstance(value, (int, float)) and lo <= float(value) <= hi


class ServerCore:
    """Yarışma sunucusu iş mantığı (HTTP'den bağımsız, thread-safe, birim-test edilir)."""

    def __init__(self, team_number=1, password="gokdogan", t0=None, seed=0, clock=time.time):
        self.team_number = team_number
        self.password = password
        self._clock = clock
        # sunucu saati başlangıcı: gerçek yarışmada keyfi bir offset olur → GCS midpoint ile bulur
        self._server_t0 = t0 if t0 is not None else 1_700_000_000.0
        self._wall_t0 = clock()
        self._lock = threading.Lock()
        self._token = None
        self._last_telemetry_wall = None
        # istatistikler (test/demo doğrulaması)
        self.stats = {
            "login_ok": 0,
            "telemetry_ok": 0,
            "telemetry_rate_reject": 0,
            "telemetry_range_reject": 0,
            "lock_posts": 0,
            "kamikaze_posts": 0,
            "qr_gets": 0,
            "hss_gets": 0,
            "clock_gets": 0,
        }
        self._telemetry_log = []  # kabul edilen son telemetriler (demo özet)
        self._synth = _SyntheticWorld(seed=seed)

    # ---- sunucu saati ----
    def server_time(self):
        """Sunucu saati (epoch-benzeri saniye). GCS midpoint offset ile bunu bulur."""
        return self._server_t0 + (self._clock() - self._wall_t0)

    def server_time_dict(self):
        """KTR /sunucusaati gövdesi: saat/dakika/saniye/milisaniye."""
        t = self.server_time()
        ms_total = int(round(t * 1000))
        return {
            "saat": (ms_total // 3_600_000) % 24,
            "dakika": (ms_total // 60_000) % 60,
            "saniye": (ms_total // 1000) % 60,
            "milisaniye": ms_total % 1000,
            "epoch": t,  # dev kolaylığı (KTR'de yok; GCS yok sayar)
        }

    # ---- oturum ----
    def login(self, body):
        team = body.get("takim_numarasi", body.get("kadi"))
        pw = body.get("sifre", body.get("parola"))
        if team not in (self.team_number, str(self.team_number)) or pw != self.password:
            raise ApiError(401, ERR_BAD_SESSION, "geçersiz takım no / şifre")
        with self._lock:
            self._token = f"tok-{int(self.server_time())}"
            self.stats["login_ok"] += 1
            return {"sonuc": 1, "token": self._token}

    def _require_session(self, headers):
        # dev'de gevşek: token varsa doğrula, yoksa da izin ver (GCS testleri login yapmadan da koşar)
        if self._token is None:
            return
        tok = headers.get("Authorization") or headers.get("authorization")
        if tok and tok.replace("Bearer ", "").strip() != self._token:
            raise ApiError(401, ERR_BAD_SESSION, "geçersiz/eksik token")

    # ---- telemetri (governor + aralık) ----
    def post_telemetry(self, body):
        # 1) hız yönetişimi: ardışık iki kabul arası ≥0.5s olmalı (>2Hz → 400/err3)
        now = self._clock()
        with self._lock:
            last = self._last_telemetry_wall
            if last is not None and (now - last) < (MIN_TELEMETRY_PERIOD_S - TELEMETRY_PERIOD_TOL_S):
                self.stats["telemetry_rate_reject"] += 1
                raise ApiError(400, ERR_RATE_LIMIT, f">2Hz telemetri reddedildi (Δt={now - last:.3f}s < 0.5s)")

        # 2) aralık doğrulama (aralık-dışı → tüm paket reddi, ceza tetikler)
        missing = [k for k in ("iha_dikilme", "iha_yonelme", "iha_yatis") if k not in body]
        if missing:
            raise ApiError(400, ERR_BAD_FIELDS, f"eksik alan: {missing}")
        checks = (
            ("iha_dikilme", body["iha_dikilme"], RANGE_DIKILME),
            ("iha_yonelme", body["iha_yonelme"], RANGE_YONELME),
            ("iha_yatis", body["iha_yatis"], RANGE_YATIS),
        )
        for name, val, (lo, hi) in checks:
            if not _in_range(val, lo, hi):
                with self._lock:
                    self.stats["telemetry_range_reject"] += 1
                raise ApiError(400, ERR_OUT_OF_RANGE, f"{name}={val} aralık dışı [{lo},{hi}]")

        with self._lock:
            self._last_telemetry_wall = now
            self.stats["telemetry_ok"] += 1
            if len(self._telemetry_log) < 5000:
                self._telemetry_log.append(
                    {
                        "t": self.server_time(),
                        "kilit": bool(body.get("iha_kilitlenme", 0)),
                        "otonom": bool(body.get("iha_otonom", 0)),
                    }
                )
        # KTR: kabul → o an aktif rakip konumları döner (GCS bunu telemetriye eş zamanlı alır)
        return {"sonuc": 1, "konumBilgileri": self._synth.opponents(self.server_time())}

    # ---- olay POST'ları ----
    def post_lock(self, body):
        with self._lock:
            self.stats["lock_posts"] += 1
        return {"sonuc": 1, "kilit_id": self.stats["lock_posts"]}

    def post_kamikaze(self, body):
        with self._lock:
            self.stats["kamikaze_posts"] += 1
        return {"sonuc": 1, "kamikaze_id": self.stats["kamikaze_posts"]}

    # ---- GET relay verileri ----
    def get_qr(self):
        with self._lock:
            self.stats["qr_gets"] += 1
        return self._synth.qr()

    def get_hss(self):
        with self._lock:
            self.stats["hss_gets"] += 1
        return {"hss_koordinat_bilgileri": self._synth.hss(self.server_time())}

    def get_opponents(self):
        return {"konumBilgileri": self._synth.opponents(self.server_time())}


class _SyntheticWorld:
    """Sentetik rakip/HSS/QR üretici — deterministik (seed), zamanla hareket eder."""

    def __init__(self, seed=0):
        import random

        self._rng = random.Random(seed)
        # merkez referans (Ankara civarı) — flat-earth küçük ofsetler
        self._lat0, self._lon0 = 39.90, 32.80
        # bir rakip: dairesel süzülür
        self._opp_team = 42
        self._opp_r = 0.0025  # ~250m
        self._opp_w = 0.05  # rad/s
        # bir HSS: sabit
        self._hss_id = 1
        # Haberleşme Dok. §10: qr_koordinati → {qrEnlem, qrBoylam}
        self._qr_coord = {"qrEnlem": self._lat0 + 0.003, "qrBoylam": self._lon0 + 0.001}

    def opponents(self, t):
        import math

        ang = self._opp_w * t
        lat = self._lat0 + self._opp_r * math.sin(ang)
        lon = self._lon0 + self._opp_r * math.cos(ang)
        yon = (math.degrees(ang) + 90.0) % 360.0
        return [
            {
                "takim_numarasi": self._opp_team,
                "iha_enlem": round(lat, 7),
                "iha_boylam": round(lon, 7),
                "iha_irtifa": 100.0,
                "iha_dikilme": 0.0,
                "iha_yonelme": round(yon, 2),
                "iha_yatis": 0.0,
                "iha_hizi": 22.0,  # Haberleşme Dok. §7.3: CEVAPTA "iha_hizi" (gönderimde iha_hiz)
                "zaman_farki": 0.2,
            }
        ]

    def hss(self, t):
        return [
            {
                "id": self._hss_id,
                "hssEnlem": self._lat0 + 0.001,
                "hssBoylam": self._lon0 + 0.0015,
                "hssYaricap": 60.0,
            }
        ]

    def qr(self):
        return dict(self._qr_coord)


# --------------------------------------------------------------------------- HTTP


class MockServerHandler(BaseHTTPRequestHandler):
    core = None  # sınıf-seviyesi paylaşılan ServerCore (server_forever öncesi set edilir)

    def log_message(self, fmt, *args):  # sessiz (test/demo çıktısını kirletme)
        pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise ApiError(400, ERR_BAD_FIELDS, f"bozuk JSON: {e}") from e

    def _send(self, status, obj):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle(self, method):
        c = self.core
        path = self.path.split("?", 1)[0].rstrip("/")
        try:
            if method == "POST" and path == "/api/giris":
                return self._send(200, c.login(self._read_json()))
            if method == "GET" and path == "/api/sunucusaati":
                c.stats["clock_gets"] += 1
                return self._send(200, c.server_time_dict())
            if method == "POST" and path == "/api/telemetri_gonder":
                c._require_session(self.headers)
                return self._send(200, c.post_telemetry(self._read_json()))
            if method == "POST" and path == "/api/kilitlenme_bilgisi":
                c._require_session(self.headers)
                return self._send(200, c.post_lock(self._read_json()))
            if method == "POST" and path == "/api/kamikaze_bilgisi":
                c._require_session(self.headers)
                return self._send(200, c.post_kamikaze(self._read_json()))
            if method == "GET" and path == "/api/qr_koordinati":
                return self._send(200, c.get_qr())
            if method == "GET" and path == "/api/hss_koordinatlari":
                return self._send(200, c.get_hss())
            if method == "GET" and path == "/api/rakip_konumlari":
                return self._send(200, c.get_opponents())
            if method == "GET" and path == "/api/_stats":  # DEV: test/demo doğrulaması
                return self._send(200, dict(c.stats))
            return self._send(404, {"sonuc": 0, "hata": "bilinmeyen endpoint", "path": path})
        except ApiError as e:
            return self._send(e.status, {"sonuc": 0, "hata_kodu": e.err_code, "mesaj": e.message})
        except Exception as e:  # noqa: BLE001 — sunucu ASLA çökmez
            return self._send(500, {"sonuc": 0, "hata_kodu": 99, "mesaj": f"iç hata: {e}"})

    def do_POST(self):
        self._handle("POST")

    def do_GET(self):
        self._handle("GET")


class MockServer:
    """ThreadingHTTPServer sarmalayıcı — start()/stop(), test için ephemeral port (port=0)."""

    def __init__(self, host="127.0.0.1", port=8081, core=None):
        self.core = core or ServerCore()
        handler = type("BoundHandler", (MockServerHandler,), {"core": self.core})
        self._httpd = ThreadingHTTPServer((host, port), handler)
        self._thread = None

    @property
    def port(self):
        return self._httpd.server_address[1]

    @property
    def host(self):
        return self._httpd.server_address[0]

    def start(self):
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=2.0)


def main():
    ap = argparse.ArgumentParser(description="GÖKDOĞAN mock yarışma sunucusu (DEV)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--team", type=int, default=1)
    ap.add_argument("--password", default="gokdogan")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--duration", type=float, default=None, help="süre sonunda dur (test)")
    args = ap.parse_args()

    core = ServerCore(team_number=args.team, password=args.password, seed=args.seed)
    srv = MockServer(host=args.host, port=args.port, core=core).start()
    print(f"MOCK_SERVER listening http://{srv.host}:{srv.port} (team={args.team})", flush=True)
    try:
        if args.duration is not None:
            time.sleep(args.duration)
        else:
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop()
        print("MOCK_SERVER_SUMMARY " + json.dumps(core.stats), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
