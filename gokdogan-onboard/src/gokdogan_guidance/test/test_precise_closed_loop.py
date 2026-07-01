"""Hassas faz kapalı-döngü + faz-flapping testi (SAD §11, Kabul Kapısı 4).

Görsel-servo PID: köşeye kayan hedef → PID → yatış/pitch → merkeze → kilit (<30s).
Kamera simülasyonu yerine basit piksel kinematiği (roll→yatay kayma). Faz FSM flapping YOK.
"""
import math

from gokdogan_guidance import controllers as C
from gokdogan_lock_validator.lock_rules import Box, LockParams, LockValidator

W, H = 1920.0, 1200.0
PHI = math.radians(45.0)
THETA = math.radians(30.0)


def test_precise_pid_centers_and_locks_under_30s():
    pid_x = C.PID(0.042, 0.0008, 0.025, -PHI, PHI)
    pid_y = C.PID(0.042, 0.0008, 0.025, -THETA, THETA)
    val = LockValidator(p=LockParams())
    # Hedef köşeye kaymış başlar
    cx, cy, size = 1350.0, 850.0, 210.0
    gain = 16000.0     # 1 rad yatış → ~16000 px/s yatay kayma (kinematik model)
    dt = 0.02          # 50Hz
    t = 0.0
    locked_at = None
    while t < 30.0:
        ex = (cx - W / 2.0) / (W / 2.0)
        ey = (cy - H / 2.0) / (H / 2.0)
        roll = pid_x.update(ex, dt)
        pitch = pid_y.update(ey, dt)
        # Kinematik (negatif geribesleme): komut hedefi merkeze taşır (her iki eksen simetrik)
        cx -= gain * roll * dt
        cy -= gain * pitch * dt
        box = Box(cx - size / 2, cy - size / 2, size, size)
        r = val.process(t, target_id=5, box=box, aircraft_alt_m=100.0, is_autonomous=True)
        if r.valid and locked_at is None:
            locked_at = t
            break
        t += dt
    assert locked_at is not None, "hassas faz kilidi üretilmeli"
    assert locked_at < 30.0, f"kilit <30s olmalı, oldu: {locked_at:.1f}s"


def test_phase_fsm_no_flapping_under_oscillation():
    """Mesafe histerezis bandında (490-510m) salınırken faz geçişi olmamalı."""
    fsm = C.PhaseFSM(enter_d=480.0, exit_d=520.0)
    transitions = 0
    prev = fsm.phase
    # Başta COARSE; 490-510 arası salınım (hiç <480 değil) → PRECISE'e girmemeli
    for i in range(200):
        d = 500.0 + 10.0 * math.sin(i * 0.3)
        p = fsm.update(d, bbox_fresh=True)
        if p != prev:
            transitions += 1
            prev = p
    assert transitions == 0, "histerezis bandında salınım faz-flapping yaratmamalı"

    # Bir kez 470'e in (PRECISE), sonra 490-510 salınım → PRECISE'te kalmalı (geri flap yok)
    fsm.update(470.0, True)
    assert fsm.phase == C.PRECISE
    back = 0
    for i in range(200):
        d = 500.0 + 15.0 * math.sin(i * 0.3)
        if fsm.update(d, True) == C.COARSE:
            back += 1
    assert back == 0, "PRECISE'ten histerezis bandında COARSE'a flapping olmamalı"
