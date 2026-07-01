"""Çoklu-hedef takip (SAD §10): Kalman + Hungarian (Cost=1−IoU, IoU≥0.3 ID koru).

Ölçüm merkez (px,py); bbox genişlik/yükseklik son tespitten taşınır. Saf Python/numpy/scipy.
"""
import numpy as np
from scipy.optimize import linear_sum_assignment

from gokdogan_tracking.kalman import KalmanBoxState


def _iou_cxcywh(a, b):
    ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2
    ax2, ay2 = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2
    bx2, by2 = b[0] + b[2] / 2, b[1] + b[3] / 2
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


class Track:
    def __init__(self, track_id, cx, cy, w, h, score):
        self.id = track_id
        self.kf = KalmanBoxState(cx, cy)
        self.w = w
        self.h = h
        self.score = score
        self.age = 0                 # kaç kare yaşadı
        self.hits = 1                # kaç kez güncellendi
        self.time_since_update = 0   # son güncellemeden bu yana kare
        self.predicted = False       # bu kare ölçümsüz (yalnız Kalman) mı

    @property
    def box(self):
        cx, cy = self.kf.pos
        return (cx, cy, self.w, self.h)

    def predict(self, dt):
        self.kf.predict(dt)
        self.age += 1
        self.time_since_update += 1
        self.predicted = self.time_since_update > 0

    def update(self, cx, cy, w, h, score):
        self.kf.update(cx, cy)
        self.w, self.h, self.score = w, h, score
        self.hits += 1
        self.time_since_update = 0
        self.predicted = False


class MultiTracker:
    def __init__(self, iou_gate=0.3, max_age=15, min_hits=1):
        self.iou_gate = iou_gate
        self.max_age = max_age       # bu kadar kare ölçümsüz kalınca sil (track loss grace)
        self.min_hits = min_hits
        self._tracks = {}
        self._next_id = 1

    @property
    def tracks(self):
        return list(self._tracks.values())

    def _associate(self, dets):
        """(matches, unmatched_tracks, unmatched_dets). dets = [(cx,cy,w,h,score),...]."""
        tracks = self.tracks
        if not tracks or not dets:
            return [], list(range(len(tracks))), list(range(len(dets)))
        cost = np.ones((len(tracks), len(dets)))
        for ti, tr in enumerate(tracks):
            for di, d in enumerate(dets):
                cost[ti, di] = 1.0 - _iou_cxcywh(tr.box, d[:4])
        row, col = linear_sum_assignment(cost)
        matches, um_tr, um_det = [], [], []
        assigned_t, assigned_d = set(), set()
        for r, c in zip(row, col):
            if (1.0 - cost[r, c]) >= self.iou_gate:   # IoU ≥ eşik → ID koru
                matches.append((r, c))
                assigned_t.add(r)
                assigned_d.add(c)
        um_tr = [i for i in range(len(tracks)) if i not in assigned_t]
        um_det = [i for i in range(len(dets)) if i not in assigned_d]
        return matches, um_tr, um_det

    def update(self, dets, dt):
        """dets: [(cx,cy,w,h,score), ...]. dt: saniye. Track listesi döndürür."""
        for tr in self._tracks.values():
            tr.predict(dt)
        tracks = self.tracks
        matches, um_tr, um_det = self._associate(dets)
        for ti, di in matches:
            tracks[ti].update(*dets[di])
        for di in um_det:
            t = Track(self._next_id, *dets[di])
            self._tracks[self._next_id] = t
            self._next_id += 1
        # Yaşlanan (uzun süre ölçümsüz) track'leri sil
        to_del = [tid for tid, tr in self._tracks.items()
                  if tr.time_since_update > self.max_age]
        for tid in to_del:
            del self._tracks[tid]
        return self.tracks

    def select_target(self, policy="largest"):
        """selected_id: target_selector (Faz 4) yoksa basit politika. -1 = yok."""
        trs = [t for t in self.tracks if t.time_since_update == 0]
        if not trs:
            return -1
        if policy == "largest":
            return max(trs, key=lambda t: t.w * t.h).id
        # merkeze en yakın
        return min(trs, key=lambda t: (t.kf.pos[0] - 960) ** 2 + (t.kf.pos[1] - 600) ** 2).id
