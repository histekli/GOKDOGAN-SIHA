"""Failsafe çekirdeği testleri (SAD §18): her tetik + öncelik + debounce + latch + İ2."""

from gokdogan_mission_fsm import failsafe_core as F
from gokdogan_mission_fsm.failsafe_core import FailsafeInputs as FI, FailsafeParams, FailsafeMonitor


def _mon(**pk):
    return FailsafeMonitor(FailsafeParams(**pk))


def test_nominal_no_action():
    m = _mon()
    act, _ = m.update(FI(now=0.0))
    assert act == F.FS_NONE


def test_battery_below_threshold_rtl():
    m = _mon(batt_rtl_pct=20.0)
    act, reason = m.update(FI(now=0.0, battery_pct=19.0))
    assert act == F.FS_RTL and "batarya" in reason


def test_battery_boundary_ok():
    m = _mon(batt_rtl_pct=20.0)
    act, _ = m.update(FI(now=0.0, battery_pct=20.0))  # tam eşik = OK (< sıkı)
    assert act == F.FS_NONE


def test_battery_zero_ignored_sitl():
    """SITL'de batarya 0/raporlanmamış → failsafe tetiklemez (yanlış-tetik önle)."""
    m = _mon(batt_rtl_pct=20.0)
    assert m.update(FI(now=0.0, battery_pct=0.0))[0] == F.FS_NONE


def test_battery_latches_after_recovery():
    """Batarya failsafe latch: seviye toparlansa bile RTL'de kalır (güvenli)."""
    m = _mon(batt_rtl_pct=20.0)
    m.update(FI(now=0.0, battery_pct=18.0))
    act, _ = m.update(FI(now=1.0, battery_pct=55.0))  # "toparlandı" ama latch
    assert act == F.FS_RTL


def test_rc_loss_debounce_then_land():
    m = _mon(rc_loss_s=5.0, rc_action=F.FS_LAND)
    assert m.update(FI(now=0.0, rc_ok=False))[0] == F.FS_NONE  # daha yeni
    assert m.update(FI(now=4.9, rc_ok=False))[0] == F.FS_NONE  # 5s dolmadı
    act, reason = m.update(FI(now=5.0, rc_ok=False))
    assert act == F.FS_LAND and "RC" in reason


def test_rc_loss_recovers_before_threshold():
    m = _mon(rc_loss_s=5.0)
    m.update(FI(now=0.0, rc_ok=False))
    m.update(FI(now=3.0, rc_ok=True))  # link geri geldi → zamanlayıcı sıfır
    assert m.update(FI(now=7.0, rc_ok=False))[0] == F.FS_NONE  # yeni sayaç, 4s < 5s
    assert m.update(FI(now=100.0, rc_ok=True))[0] == F.FS_NONE


def test_gcs_loss_10s_rtl():
    m = _mon(gcs_loss_s=10.0)
    assert m.update(FI(now=0.0, gcs_ok=False))[0] == F.FS_NONE
    act, reason = m.update(FI(now=10.0, gcs_ok=False))
    assert act == F.FS_RTL and "GCS" in reason


def test_gps_glitch_land():
    m = _mon(gps_glitch_s=2.0)
    assert m.update(FI(now=0.0, gps_ok=False))[0] == F.FS_NONE
    act, _ = m.update(FI(now=2.0, gps_ok=False))
    assert act == F.FS_LAND


def test_geofence_instant_rtl():
    m = _mon()
    act, reason = m.update(FI(now=0.0, geofence_ok=False))
    assert act == F.FS_RTL and "geofence" in reason


def test_node_health_rtl():
    m = _mon()
    act, reason = m.update(FI(now=0.0, node_health_ok=False))
    assert act == F.FS_RTL and "node" in reason


def test_rc_override_supreme():
    """RC override her şeyi ezer: batarya + geofence olsa bile MANUAL."""
    m = _mon()
    act, reason = m.update(FI(now=0.0, rc_override=True, battery_pct=5.0, geofence_ok=False))
    assert act == F.FS_MANUAL and "pilot" in reason


def test_mission_link_loss_is_not_failsafe():
    """KIRMIZI ÇİZGİ İ2: Wi-Fi mission_link kaybı → failsafe DEĞİL (otonom devam)."""
    m = _mon()
    act, _ = m.update(FI(now=0.0, mission_link_ok=False))
    assert act == F.FS_NONE


def test_priority_gps_over_battery():
    """GPS glitch (LAND) önceliği batarya (RTL) önünde — RTL GPS gerektirir."""
    m = _mon(gps_glitch_s=0.0, batt_rtl_pct=20.0)
    act, _ = m.update(FI(now=0.0, gps_ok=False, battery_pct=10.0))
    assert act == F.FS_LAND


def test_on_ground_no_failsafe():
    m = _mon()
    act, _ = m.update(FI(now=0.0, battery_pct=5.0, armed=False, in_flight=False))
    assert act == F.FS_NONE


def test_reset_clears_latch():
    m = _mon(batt_rtl_pct=20.0)
    m.update(FI(now=0.0, battery_pct=10.0))
    m.reset()
    assert m.update(FI(now=1.0, battery_pct=90.0))[0] == F.FS_NONE
