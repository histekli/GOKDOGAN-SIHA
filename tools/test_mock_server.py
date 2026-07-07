"""mock_server + GameServerClient testleri (SAD §15, Faz 6).

Doğrular: ≤2Hz governor (>2Hz→400/err3), aralık doğrulama (dikilme/yonelme/yatis→400/err4),
ServerClock midpoint offset (+monotonik), telemetri aralık-CLAMP (paket reddini önler),
kilit/kamikaze POST, QR/HSS GET, oturum. Testler container'da (colcon değil, doğrudan pytest).
"""

import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mock_server as MS  # noqa: E402
import mock_gcs as MG  # noqa: E402

# --------------------------------------------------------------- ServerCore (saf)


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_login_ok_and_bad():
    core = MS.ServerCore(team_number=7, password="pw")
    assert core.login({"takim_numarasi": 7, "sifre": "pw"})["sonuc"] == 1
    with pytest.raises(MS.ApiError) as e:
        core.login({"takim_numarasi": 7, "sifre": "yanlis"})
    assert e.value.status == 401 and e.value.err_code == MS.ERR_BAD_SESSION


def test_telemetry_rate_governor_rejects_over_2hz():
    clk = FakeClock()
    core = MS.ServerCore(clock=clk)
    body = {"iha_dikilme": 0.0, "iha_yonelme": 100.0, "iha_yatis": 0.0}
    assert core.post_telemetry(body)["sonuc"] == 1  # ilk kabul
    clk.t += 0.1  # 0.1s sonra → 10Hz → red
    with pytest.raises(MS.ApiError) as e:
        core.post_telemetry(body)
    assert e.value.status == 400 and e.value.err_code == MS.ERR_RATE_LIMIT
    clk.t += 0.5  # toplam 0.6s → kabul
    assert core.post_telemetry(body)["sonuc"] == 1
    assert core.stats["telemetry_rate_reject"] == 1


@pytest.mark.parametrize(
    "field,val",
    [
        ("iha_dikilme", 91.0),
        ("iha_dikilme", -91.0),
        ("iha_yonelme", 360.1),
        ("iha_yonelme", -0.1),
        ("iha_yatis", 90.1),
        ("iha_yatis", -90.1),
    ],
)
def test_telemetry_out_of_range_rejected(field, val):
    core = MS.ServerCore()
    body = {"iha_dikilme": 0.0, "iha_yonelme": 100.0, "iha_yatis": 0.0}
    body[field] = val
    with pytest.raises(MS.ApiError) as e:
        core.post_telemetry(body)
    assert e.value.status == 400 and e.value.err_code == MS.ERR_OUT_OF_RANGE
    assert core.stats["telemetry_range_reject"] == 1


def test_telemetry_boundaries_accepted():
    core = MS.ServerCore()
    for body in ({"iha_dikilme": 90.0, "iha_yonelme": 0.0, "iha_yatis": -90.0},):
        assert core.post_telemetry(body)["sonuc"] == 1


def test_server_time_monotonic():
    clk = FakeClock()
    core = MS.ServerCore(t0=5000.0, clock=clk)
    t1 = core.server_time()
    clk.t += 2.0
    t2 = core.server_time()
    assert t2 - t1 == pytest.approx(2.0)
    assert t1 == pytest.approx(5000.0)


def test_synthetic_world_shapes():
    core = MS.ServerCore(seed=0)
    opp = core.get_opponents()["konumBilgileri"]
    assert opp and {"takim_numarasi", "iha_enlem", "iha_boylam"} <= set(opp[0])
    hss = core.get_hss()["hss_koordinat_bilgileri"]
    assert hss and {"id", "hssEnlem", "hssBoylam", "hssYaricap"} <= set(hss[0])
    qr = core.get_qr()
    assert {"qrEnlem", "qrBoylam"} <= set(qr)  # Haberleşme Dok. §10


# ------------------------------------------------------- ServerClock / HzMeter


def test_server_clock_midpoint_offset():
    ck = MG.ServerClock()
    # t_send=100, t_recv=102 (RTT=2, midpoint=101); sunucu 101 anında 5000 dedi → offset≈4899
    ck.update(100.0, 5000.0, 102.0)
    assert ck.offset == pytest.approx(4899.0)
    assert ck.synced
    # daha düşük RTT'li örnek offset'i günceller; yüksek RTT'li yok sayılır
    ck.update(200.0, 5100.0, 200.5)  # RTT=0.5 < 2 → kabul
    assert ck.offset == pytest.approx(5100.0 - 200.25)


def test_server_clock_output_monotonic():
    ck = MG.ServerClock()
    ck.update(0.0, 1e12, 0.0)  # kocaman ileri offset
    a = ck.now()
    b = ck.now()
    assert b >= a


def test_hz_meter_enforces_2hz():
    m = MG.TelemetryHzMeter(max_hz=2.0)
    assert m.allow(now=0.0)
    m.record(now=0.0)
    assert not m.allow(now=0.3)  # 0.3s < 0.5s → engelle
    assert m.allow(now=0.6)  # 0.6s ≥ 0.5s → izin


# --------------------------------------------------- Uçtan uca (canlı HTTP)


@pytest.fixture()
def live_server():
    srv = MS.MockServer(port=0, core=MS.ServerCore(team_number=7, password="pw", seed=1)).start()
    yield srv
    srv.stop()


def _client(srv):
    return MG.GameServerClient(f"http://{srv.host}:{srv.port}", team=7, password="pw")


def test_client_login_and_clock(live_server):
    c = _client(live_server)
    assert c.login()
    assert c.sync_clock()
    assert c.clock.synced


def test_client_telemetry_governed_and_clamped(live_server):
    c = _client(live_server)
    c.login()
    flight = {"iha_dikilme": 3.0, "iha_yonelme": 270.0, "iha_yatis": -2.0}
    assert c.send_telemetry(flight, now=0.0) is True
    assert c.send_telemetry(flight, now=0.2) is False  # governor (client-side) engeller
    assert c.stats["telemetry_governed"] == 1
    # aralık-dışı → clamp → sunucu KABUL eder (paket reddi/−0.2 yok)
    # sunucu governor'ı GERÇEK duvar-saatinde → kabul için gerçek ≥0.5s bekle
    time.sleep(0.55)
    bad = {"iha_dikilme": -200.0, "iha_yonelme": 999.0, "iha_yatis": 200.0}
    assert c.send_telemetry(bad, now=1.0) is True
    assert c.stats["telemetry_clamped"] == 3
    assert live_server.core.stats["telemetry_range_reject"] == 0


def test_server_rejects_uncklamped_out_of_range(live_server):
    """GameServerClient clamp'i atlanırsa sunucu reddeder (GCS'in doğru davrandığını doğrular)."""
    c = _client(live_server)
    c.login()
    status, obj = c._request(
        "POST", "/api/telemetri_gonder", {"iha_dikilme": 0.0, "iha_yonelme": 999.0, "iha_yatis": 0.0}
    )
    assert status == 400 and obj["hata_kodu"] == MS.ERR_OUT_OF_RANGE


def test_client_events_and_relay_gets(live_server):
    c = _client(live_server)
    c.login()
    assert c.post_lock({"target_id": 5, "lock_end_ts": 123.0})
    assert c.post_kamikaze({"success": True, "qr_text": "GOKDOGAN42"})
    assert c.get_qr() is not None
    hss = c.get_hss()
    assert hss and hss[0]["id"] == 1
    s = live_server.core.stats
    assert s["lock_posts"] == 1 and s["kamikaze_posts"] == 1
    assert s["qr_gets"] == 1 and s["hss_gets"] == 1
