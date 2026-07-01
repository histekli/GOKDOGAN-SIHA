"""Güdüm denetleyici testleri (SAD §11): PID anti-windup, PN guard, rate/LPF, faz-FSM flapping."""
from gokdogan_guidance import controllers as C


def test_pid_proportional_and_clamp():
    pid = C.PID(kp=1.0, ki=0.0, kd=0.0, out_min=-45.0, out_max=45.0)
    assert pid.update(10.0, 0.1) == 10.0
    assert pid.update(1000.0, 0.1) == 45.0        # çıkış clamp


def test_pid_anti_windup():
    # Sürekli doyuran hata → integral sınırsız birikmemeli (windup yok)
    pid = C.PID(kp=0.0, ki=1.0, kd=0.0, out_min=-5.0, out_max=5.0, i_limit=5.0)
    for _ in range(100):
        pid.update(100.0, 0.1)
    assert abs(pid._i) <= 5.0 + 1e-6, "integral i_limit'i aşmamalı"
    # Hata işaret değiştirince hızlı toparlanır (aşırı windup yok)
    out = pid.update(-1.0, 0.1)
    assert out < 5.0


def test_pn_divide_guard():
    assert C.pn_accel(v_closing=0.0, los_rate=1.0, n=4.0) == 0.0     # V_c≈0 → 0
    assert C.pn_accel(v_closing=0.1, los_rate=1.0, n=4.0, v_eps=0.5) == 0.0
    assert C.pn_accel(v_closing=30.0, los_rate=0.05, n=4.0) == 4.0 * 30.0 * 0.05


def test_rate_limiter():
    rl = C.RateLimiter(max_rate=20.0)   # 20 birim/s
    rl.reset(0.0)
    y = rl.update(100.0, dt=0.1)         # en fazla 2 birim değişebilir
    assert abs(y - 2.0) < 1e-6


def test_lpf_smooths():
    lpf = C.LPF(alpha=0.3)
    lpf.reset(0.0)
    y1 = lpf.update(10.0)
    assert 0.0 < y1 < 10.0               # anında sıçramaz
    assert abs(y1 - 3.0) < 1e-6          # 0.3*10 + 0.7*0


def test_phase_fsm_hysteresis_no_flapping():
    fsm = C.PhaseFSM(enter_d=480.0, exit_d=520.0)
    assert fsm.phase == C.COARSE
    # 500m + taze bbox: enter_d(480) ile exit_d(520) arasında → PRECISE'e GİRMEZ
    assert fsm.update(500.0, True) == C.COARSE
    # 470m taze → PRECISE
    assert fsm.update(470.0, True) == C.PRECISE
    # 500m'e geri: exit_d(520) altında → PRECISE'te KALIR (flapping yok)
    assert fsm.update(500.0, True) == C.PRECISE
    # bbox bayat → COARSE
    assert fsm.update(500.0, False) == C.COARSE


def test_phase_fsm_requires_fresh_bbox_to_enter():
    fsm = C.PhaseFSM()
    assert fsm.update(400.0, False) == C.COARSE   # yakın ama bbox bayat → precise'e girmez


def test_pinhole_distance():
    # W=2m, f=1100px, bbox 44px → d = 2*1100/44 = 50m
    assert abs(C.estimate_distance_pinhole(44.0, 2.0, 1100.0) - 50.0) < 1e-6
