"""Inference abstraction (SAD §10). backend:=mock|onnxruntime|tensorrt.

Dev: mock (sentetik hedefte renk-blob tespiti, deterministik) veya ONNX Runtime CPU.
tensorrt: ⚠️ ON-DEVICE (Jetson'da trtexec .plan). ROI merkez %70 → 640×640 → koordinat geri 1920×1200.
Detection = (cx, cy, w, h, score) tam 1920×1200 uzayında.
"""
import numpy as np

INFER_W, INFER_H = 640, 640


def roi_crop(frame, roi_frac=0.7):
    """Merkez %roi_frac bölgeyi kırp. (crop, x_off, y_off) döndürür."""
    h, w = frame.shape[:2]
    cw, ch = int(w * roi_frac), int(h * roi_frac)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    return frame[y0:y0 + ch, x0:x0 + cw], x0, y0


class MockDetector:
    """Deterministik renk-blob tespiti (sentetik kırmızı hedef). YOLO yerine dev mock."""

    def __init__(self, roi_frac=0.7, min_area=100):
        self.roi_frac = roi_frac
        self.min_area = min_area

    def detect(self, frame):
        import cv2
        crop, x0, y0 = roi_crop(frame, self.roi_frac)
        ch, cw = crop.shape[:2]
        small = cv2.resize(crop, (INFER_W, INFER_H))
        sx, sy = cw / INFER_W, ch / INFER_H
        # Kırmızı maske (BGR): R yüksek, G/B düşük
        b, g, r = small[:, :, 0], small[:, :, 1], small[:, :, 2]
        mask = ((r > 120) & (g < 80) & (b < 80)).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        dets = []
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            if bw * bh < self.min_area:
                continue
            # 640 → crop → tam kare koordinatına geri ölçekle
            fx = x0 + x * sx
            fy = y0 + y * sy
            fw = bw * sx
            fh = bh * sy
            dets.append((fx + fw / 2.0, fy + fh / 2.0, fw, fh, 0.9))
        return dets


class OnnxDetector:
    """ONNX Runtime CPU (dev, model .onnx gerekir). Model yoksa AÇIK hata (çökme değil)."""

    def __init__(self, model_path, roi_frac=0.7, conf=0.35):
        import os
        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(
                f"ONNX model yok: {model_path} — YOLOv11s ONNX'i /models'a koyun (Emircan).")
        import onnxruntime as ort
        self.sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.roi_frac = roi_frac
        self.conf = conf

    def detect(self, frame):
        # ⚠️ Model çıktı formatına (YOLOv11) göre postprocess Emircan tarafından bağlanır.
        raise NotImplementedError("ONNX postprocess YOLOv11 çıktı formatına göre bağlanacak (Emircan).")


class TensorRTDetector:
    """⚠️ ON-DEVICE DOĞRULAMA GEREKİR — Jetson TensorRT FP16 (.plan). x86'da çalışmaz."""

    def __init__(self, engine_path, **kw):
        raise NotImplementedError(
            "TensorRT yolu ⚠️ ON-DEVICE (Jetson): trtexec ile ONNX→.plan, pycuda/TRT runtime. "
            "x86 dev'de mock/onnxruntime kullanın.")

    def detect(self, frame):
        raise NotImplementedError("⚠️ ON-DEVICE")


def make_detector(backend, **kw):
    if backend == "mock":
        return MockDetector(**{k: v for k, v in kw.items() if k in ("roi_frac", "min_area")})
    if backend == "onnxruntime":
        return OnnxDetector(kw.get("model_path", ""),
                            roi_frac=kw.get("roi_frac", 0.7), conf=kw.get("conf", 0.35))
    if backend == "tensorrt":
        return TensorRTDetector(kw.get("engine_path", ""))
    raise ValueError(f"bilinmeyen inference backend: {backend}")
