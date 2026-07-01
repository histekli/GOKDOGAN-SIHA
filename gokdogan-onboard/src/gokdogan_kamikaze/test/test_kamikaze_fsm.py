"""Kamikaze FSM testleri (SAD §12): faz geçişleri + guard'lar (min-alt pull-up, G clamp, 2 deneme)."""
from gokdogan_kamikaze.kamikaze_fsm import (
    KamikazeFsm, KamikazeParams, INTIKAL, DALIS, QR, PULLUP, DONE,
)


def test_full_sequence_with_qr():
    f = KamikazeFsm()
    f.start()
    assert f.s.phase == INTIKAL
    f.update(alt_agl=100.0, airspeed=29.0, aligned=True)      # 100m + hizalı → DALIS
    assert f.s.phase == DALIS
    assert abs(f.commanded_pitch() - (-45.0)) < 1e-6          # dalış −45°
    f.update(alt_agl=48.0, airspeed=29.0)                     # 50m altı → QR
    assert f.s.phase == QR
    f.update(alt_agl=40.0, airspeed=29.0, qr_found=True, qr_text="TF-2026")  # QR → PULLUP
    assert f.s.phase == PULLUP
    f.update(alt_agl=85.0, airspeed=25.0)                     # güvenli irtifa → DONE
    assert f.s.phase == DONE
    assert f.s.qr_text == "TF-2026"


def test_qr_not_found_min_alt_pullup():
    """QR bulunamadı ama min irtifa → KESİN GÜVENLİK pull-up (her halükarda)."""
    f = KamikazeFsm()
    f.start()
    f.update(100.0, 29.0, aligned=True)
    f.update(48.0, 29.0)
    assert f.s.phase == QR
    f.update(28.0, 29.0, qr_found=False)     # min_pullup_alt(30) altı, QR yok → PULLUP
    assert f.s.phase == PULLUP
    assert "min-alt" in f.s.detail


def test_g_clamp_never_exceeds_limit():
    f = KamikazeFsm(KamikazeParams(pullup_g=5.0, g_limit=3.0))
    assert f.commanded_g() == 3.0            # 2.7 değil ama 5>3 → 3'e clamp


def test_two_attempt_limit():
    f = KamikazeFsm()
    f.start()
    # 1. deneme: QR yok → min-alt pull-up → güvenli irtifa → INTIKAL (tekrar)
    f.update(100.0, 29.0); f.update(48.0, 29.0); f.update(28.0, 29.0)
    assert f.s.phase == PULLUP
    f.update(85.0, 25.0)                      # QR yok → attempt=1 → INTIKAL
    assert f.s.phase == INTIKAL and f.s.attempts == 1
    # 2. deneme: yine QR yok → pull-up → 2 deneme doldu → DONE
    f.update(100.0, 29.0); f.update(48.0, 29.0); f.update(28.0, 29.0)
    f.update(85.0, 25.0)
    assert f.s.phase == DONE and f.s.attempts == 2


def test_dive_holds_pitch():
    f = KamikazeFsm()
    f.start()
    f.update(100.0, 29.0)
    assert f.s.phase == DALIS
    assert f.commanded_pitch() == -45.0
