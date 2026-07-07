"""Watchdog testleri (SAD §18 katman-3): bayat kritik node tespiti + heartbeat + grace."""

from gokdogan_common.watchdog import Watchdog


def test_never_beat_is_stale():
    w = Watchdog(timeout_s=3.0)
    w.register("perception")
    assert "perception" in w.stale(now=0.0)
    assert not w.healthy(now=0.0)


def test_register_with_now_grace():
    w = Watchdog(timeout_s=3.0)
    w.register("guidance", now=100.0)  # kayıt = ilk heartbeat
    assert w.healthy(now=101.0)  # grace içinde
    assert not w.healthy(now=105.0)  # 5s > 3s timeout


def test_beat_keeps_alive():
    w = Watchdog(timeout_s=2.0)
    w.register("hss", now=0.0)
    w.beat("hss", now=1.0)
    w.beat("hss", now=2.5)
    assert w.healthy(now=3.0)  # son atış 2.5 → yaş 0.5 < 2
    assert not w.healthy(now=5.0)  # yaş 2.5 > 2


def test_non_required_does_not_break_health():
    w = Watchdog(timeout_s=1.0)
    w.register("optional", required=False)
    assert w.healthy(now=100.0)  # kritik değil → sağlığı bozmaz
    assert "optional" in w.stale(now=100.0)


def test_stale_required_list():
    w = Watchdog(timeout_s=1.0)
    w.register("a", now=0.0)
    w.register("b", now=0.0)
    w.beat("a", now=10.0)
    assert w.stale_required(now=10.5) == ["b"]
    assert not w.healthy(now=10.5)
