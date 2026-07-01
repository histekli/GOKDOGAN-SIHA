"""Kamera kaynağı abstraction (SAD §10). source:=synthetic|video|gazebo|usb.

Dev: synthetic (bilinen ground-truth bbox'lı hareketli hedef) + video dosyası.
gazebo: ROS /camera/image aboneliği (node'da). usb: ⚠️ ON-DEVICE GStreamer.
Kamera 1920×1200 (AR0234). Saf numpy/opencv — donanımsız test edilebilir.
"""
import numpy as np

W, H = 1920, 1200


class SyntheticCamera:
    """Deterministik hareketli hedef: köşeden başlar, merkeze yaklaşır ve büyür, sonra kilitte kalır.

    read() → (frame_bgr uint8, gt_box (x,y,w,h) | None). Bilinen ground-truth ile mock/tracking testi.
    """

    def __init__(self, fps=50.0, seed=0, approach_s=2.0, hold_s=4.5, size_hold=210):
        self.fps = fps
        self.dt = 1.0 / fps
        self.t = 0.0
        self.approach_s = approach_s
        self.hold_s = hold_s
        self.size_hold = size_hold
        self._rng = np.random.default_rng(seed)

    @property
    def done(self):
        return self.t > (self.approach_s + self.hold_s + 0.5)

    def _target(self):
        """Zamanın fonksiyonu olarak (cx, cy, size). approach: köşeden merkeze + büyüme."""
        cx0, cy0, size0 = 300.0, 300.0, 60.0
        cxf, cyf, sizef = W / 2.0, H / 2.0, float(self.size_hold)
        if self.t < self.approach_s:
            a = self.t / self.approach_s
            cx = cx0 + (cxf - cx0) * a
            cy = cy0 + (cyf - cy0) * a
            size = size0 + (sizef - size0) * a
        else:
            # merkezde küçük gürültüyle sabit (kilit için kararlı)
            jit = self._rng.normal(0, 2.0, 2)
            cx, cy, size = cxf + jit[0], cyf + jit[1], sizef
        return cx, cy, size

    def read(self):
        if self.done:
            return None, None
        cx, cy, size = self._target()
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        x1 = int(cx - size / 2)
        y1 = int(cy - size / 2)
        x2 = int(cx + size / 2)
        y2 = int(cy + size / 2)
        frame[max(0, y1):min(H, y2), max(0, x1):min(W, x2)] = (0, 0, 255)  # kırmızı hedef (BGR)
        gt = (float(x1), float(y1), float(size), float(size))
        self.t += self.dt
        return frame, gt


class VideoCamera:
    """Kayıtlı video dosyası (hızlı iterasyon). read() → (frame, None)."""

    def __init__(self, path):
        import cv2
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise RuntimeError(f"video açılamadı: {path}")
        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0

    def read(self):
        ok, frame = self._cap.read()
        if not ok:
            return None, None
        return frame, None


def make_camera(source, **kw):
    if source == "synthetic":
        return SyntheticCamera(**{k: v for k, v in kw.items()
                                  if k in ("fps", "seed", "approach_s", "hold_s", "size_hold")})
    if source == "video":
        return VideoCamera(kw["path"])
    if source in ("gazebo", "usb"):
        # gazebo: ROS aboneliği node'da; usb: ⚠️ ON-DEVICE GStreamer (v4l2src). Burada değil.
        raise RuntimeError(f"'{source}' kaynağı node katmanında ele alınır (⚠️ usb ON-DEVICE)")
    raise ValueError(f"bilinmeyen kamera kaynağı: {source}")
