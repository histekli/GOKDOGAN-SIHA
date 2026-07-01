"""Algı pipeline entegrasyon testi (SAD §10, Kabul Kapısı 3):
sentetik hedef → mock tespit → Kalman/Hungarian takip → kilit denetimi → DOĞRU lock_event.

Saf Python (ROS'suz) — deterministik, hızlı, cross-process DDS yok.
"""
from gokdogan_perception.camera import SyntheticCamera
from gokdogan_perception.inference import MockDetector
from gokdogan_tracking.tracker import MultiTracker
from gokdogan_lock_validator.lock_rules import Box, LockParams, LockValidator


def _run(alt=100.0, autonomous=True):
    cam = SyntheticCamera(fps=50.0, seed=1, approach_s=2.0, hold_s=4.5)
    det = MockDetector()
    trk = MultiTracker(max_age=15)
    val = LockValidator(p=LockParams())
    t = 0.0
    events = []
    detections_seen = 0
    frame_idx = 0
    while True:
        frame, _gt = cam.read()
        if frame is None:
            break
        # YOLO her 5 karede (SAD); aralarda tespit yenilenmez → tracker predict-only
        if frame_idx % 5 == 0:
            dets = det.detect(frame)
        else:
            dets = []
        detections_seen += len(dets)
        tracks = trk.update(dets, dt=cam.dt)
        sel = trk.select_target("largest")
        if sel != -1:
            tr = next(x for x in tracks if x.id == sel)
            cx, cy, w, h = tr.box
            box = Box(cx - w / 2, cy - h / 2, w, h)
            r = val.process(t, sel, box, aircraft_alt_m=alt, is_autonomous=autonomous)
            if r.valid:
                events.append((round(t, 2), sel))
        frame_idx += 1
        t += cam.dt
    return events, detections_seen


def test_synthetic_produces_valid_lock():
    events, dets = test = _run()
    assert dets > 0, "mock tespit hiç detection üretmedi"
    assert events, "sentetik senaryoda geçerli lock_event üretilmeli"
    first_t = events[0][0]
    # Hedef ~2s'de merkeze gelir, ~4s tutunca kilit → ~6s civarı
    assert 5.0 <= first_t <= 8.0, f"kilit ~6s'de beklenirdi, oldu: {first_t}"


def test_no_lock_when_not_autonomous():
    events, _ = _run(autonomous=False)
    assert not events, "otonom değilken kilit olmamalı (Kural 5)"


def test_no_lock_when_grounded():
    events, _ = _run(alt=2.0)
    assert not events, "yerdeyken/alçakken kilit olmamalı (Kural 4)"
