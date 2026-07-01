"""Kilit kuralları birim testleri (SAD §7). HER kural için ayrı test (prompt Faz 3)."""
import pytest

from gokdogan_lock_validator import lock_rules as L
from gokdogan_lock_validator.lock_rules import Box, LockParams, LockValidator

P = LockParams()
# Kilit dörtgeni: merkez 960×600 @ (480,300)-(1440,900). "on-target" örnek kutu:
ON = Box(860.0, 500.0, 200.0, 200.0)     # merkezde, alan 40000 (≥%6), tam içeride


# ---- Kural 1: merkez ----
def test_rule_center_pass_and_fail():
    assert L.rule_center(ON, P)
    assert not L.rule_center(Box(0, 0, 200, 200), P)        # köşede
    assert not L.rule_center(Box(1400, 600, 100, 100), P)   # merkezi dörtgen dışında


# ---- Kural 2: boyut ----
def test_rule_size_pass_and_fail():
    assert L.rule_size(ON, P)                                # 40000/576000 ≈ 0.069 ≥ 0.06
    assert not L.rule_size(Box(950, 590, 50, 50), P)         # 2500/576000 ≈ 0.004 < 0.06


# ---- Kural 3: içerme (≥%90 kilit dörtgeni içinde) ----
def test_rule_containment_pass_and_fail():
    assert L.rule_containment(ON, P)                         # tam içeride → 1.0
    assert not L.rule_containment(Box(1400, 500, 200, 200), P)  # yarısı dışarıda


# ---- Kural 4: yerdeki hedef / irtifa ----
def test_rule_not_ground():
    assert L.rule_not_ground(100.0, P)
    assert not L.rule_not_ground(2.0, P)                     # min 5m altında


# ---- Kural 5: otonom mod ----
def test_rule_autonomous():
    assert L.rule_autonomous(True)
    assert not L.rule_autonomous(False)


# ---- instant_ok bileşimi ----
def test_instant_ok_combines_all():
    assert L.instant_ok(ON, 100.0, True, P)
    assert not L.instant_ok(ON, 100.0, False, P)             # otonom değil
    assert not L.instant_ok(ON, 2.0, True, P)                # yerde
    assert not L.instant_ok(Box(0, 0, 50, 50), 100.0, True, P)  # merkez+boyut fail


# ---- Zaman penceresi: 4s kesintisiz → geçerli ----
def test_temporal_valid_after_4s():
    v = LockValidator(p=P)
    valid_at = None
    t = 0.0
    while t <= 4.5:
        r = v.process(t, target_id=7, box=ON, aircraft_alt_m=100.0, is_autonomous=True)
        if r.valid and valid_at is None:
            valid_at = t
        t += 0.1
    assert valid_at is not None
    assert 3.9 <= valid_at <= 4.15, f"kilit ~4s'de olmalı, oldu: {valid_at}"


def test_temporal_tolerates_small_gap():
    v = LockValidator(p=P)
    got = False
    # 0..3.85 on, sonra 0.15s boşluk (tolerans içi), sonra 4.0..4.2 on
    times = [round(x * 0.05, 2) for x in range(0, 78)]      # 0..3.85
    times += [4.0, 4.05, 4.10, 4.15]                        # 0.15s boşluk sonrası
    for t in times:
        r = v.process(t, 7, ON, 100.0, True)
        got = got or r.valid
    assert got, "≤200ms boşluk kiliti bozmamalı"


def test_temporal_big_gap_resets():
    v = LockValidator(p=P)
    # 0..2.0 on, sonra 0.5s boşluk (tolerans dışı) → yeniden başlar
    early_valid = False
    t = 0.0
    while t <= 2.0:
        v.process(t, 7, ON, 100.0, True)
        t += 0.1
    # 2.0 → 2.5 boşluk (off) sonra devam; 4.0'da (orijinal start'tan 4s) HENÜZ geçerli olmamalı
    t = 2.5
    while t <= 4.1:
        r = v.process(t, 7, ON, 100.0, True)
        if t <= 4.05 and r.valid:
            early_valid = True
        t += 0.1
    assert not early_valid, "büyük boşluk sonrası kilit sıfırlanmalı (4s yeniden gerekir)"


# ---- last_locked_id: ardışık aynı hedef yasak ----
def test_last_locked_id_forbids_consecutive():
    v = LockValidator(p=P)
    # id=7 kilitle
    t = 0.0
    while t <= 4.2:
        r = v.process(t, 7, ON, 100.0, True)
        t += 0.1
    assert v.last_locked_id == 7
    # id=7 tekrar → asla geçerli olmamalı
    t2 = 4.2
    again = False
    while t2 <= 9.0:
        r = v.process(t2, 7, ON, 100.0, True)
        again = again or r.valid
        t2 += 0.1
    assert not again, "aynı hedefe (last_locked_id) ardışık kilit yasak"
    # farklı hedef id=8 → kilitlenebilir
    t3 = 9.0
    other = False
    while t3 <= 13.5:
        r = v.process(t3, 8, ON, 100.0, True)
        other = other or r.valid
        t3 += 0.1
    assert other, "farklı hedef kilitlenebilmeli"
