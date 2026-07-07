"""mission_link LinkStats testleri (SAD §22): seq-kayıp %, gecikme, sıra-dışı/tekrar."""

from gokdogan_mission_link.metrics import LinkStats


def test_no_loss():
    s = LinkStats()
    for seq in range(1, 11):
        s.observe(seq)
    assert s.received == 10 and s.lost == 0 and s.loss_pct == 0.0


def test_gap_counts_loss():
    s = LinkStats()
    s.observe(1)
    s.observe(2)
    s.observe(6)  # 3,4,5 kayıp
    assert s.lost == 3
    # total = received(3) + lost(3) = 6 → %50
    assert s.loss_pct == 50.0


def test_duplicate_and_reorder_dont_regress():
    s = LinkStats()
    s.observe(5)
    s.observe(5)  # tekrar
    s.observe(3)  # sıra-dışı (geç gelen)
    assert s.duplicates == 1 and s.reordered == 1
    assert s.last_seq == 5  # geriye gitmez
    assert s.lost == 0


def test_latency_avg():
    s = LinkStats()
    s.observe(1, ts=100.0, now=100.2)  # 0.2s
    s.observe(2, ts=101.0, now=101.4)  # 0.4s
    assert s.latency_last == 0.4
    assert abs(s.latency_avg - 0.3) < 1e-6


def test_negative_latency_clamped():
    s = LinkStats()
    s.observe(1, ts=100.0, now=99.5)  # saat kayması → negatif → 0'a clamp
    assert s.latency_last == 0.0


def test_snapshot_shape():
    s = LinkStats()
    s.observe(1, ts=0.0, now=0.1)
    snap = s.snapshot()
    assert {"received", "lost", "loss_pct", "latency_avg_s"} <= set(snap)
