"""Takip birim testleri (SAD §10): ID kararlılığı, ilişkilendirme, predict-only, silme."""
from gokdogan_tracking.tracker import MultiTracker, _iou_cxcywh


def test_iou_basic():
    assert _iou_cxcywh((100, 100, 50, 50), (100, 100, 50, 50)) == 1.0
    assert _iou_cxcywh((0, 0, 10, 10), (100, 100, 10, 10)) == 0.0


def test_single_target_id_stable():
    t = MultiTracker()
    tid = None
    x = 500.0
    for _ in range(10):
        tracks = t.update([(x, 600.0, 80.0, 80.0, 0.9)], dt=0.1)
        x += 10.0  # sağa hareket
        assert len(tracks) == 1
        if tid is None:
            tid = tracks[0].id
        assert tracks[0].id == tid, "hareket eden tek hedef ID'sini korumalı"


def test_two_separated_targets_distinct_ids():
    t = MultiTracker()
    for _ in range(5):
        tracks = t.update([(300.0, 300.0, 60.0, 60.0, 0.9),
                           (1500.0, 900.0, 60.0, 60.0, 0.9)], dt=0.1)
    ids = {tr.id for tr in tracks}
    assert len(ids) == 2, "iyi ayrık iki hedef iki farklı ID"


def test_missed_detection_predict_only():
    t = MultiTracker(max_age=15)
    t.update([(500.0, 600.0, 80.0, 80.0, 0.9)], dt=0.1)
    tid = t.tracks[0].id
    # 3 kare ölçümsüz → track yaşar, predicted=True
    for _ in range(3):
        tracks = t.update([], dt=0.1)
    assert any(tr.id == tid for tr in tracks), "kısa süre ölçümsüz track silinmemeli"
    tr = [x for x in tracks if x.id == tid][0]
    assert tr.predicted and tr.time_since_update == 3


def test_track_deleted_after_max_age():
    t = MultiTracker(max_age=5)
    t.update([(500.0, 600.0, 80.0, 80.0, 0.9)], dt=0.1)
    for _ in range(7):
        tracks = t.update([], dt=0.1)
    assert tracks == [], "max_age aşılınca track silinmeli"


def test_far_detection_new_id_not_switch():
    t = MultiTracker(iou_gate=0.3)
    t.update([(500.0, 600.0, 80.0, 80.0, 0.9)], dt=0.1)
    first = t.tracks[0].id
    # Çok uzak tespit (IoU<0.3) → yeni ID, eski track'e atanmaz (ID-switch yok)
    tracks = t.update([(1500.0, 200.0, 80.0, 80.0, 0.9)], dt=0.1)
    new_ids = {tr.id for tr in tracks}
    assert first in new_ids  # eski track hâlâ var (predicted)
    assert len(new_ids) == 2  # yeni hedef ayrı ID aldı


def test_select_target_largest():
    t = MultiTracker()
    tracks = t.update([(300.0, 300.0, 40.0, 40.0, 0.8),
                       (1500.0, 900.0, 120.0, 120.0, 0.9)], dt=0.1)
    sel = t.select_target("largest")
    big = max(tracks, key=lambda x: x.w * x.h)
    assert sel == big.id
