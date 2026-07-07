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
    """ONNX Runtime CPU (dev). YOLOv8/v11 (ultralytics) ONNX modeli. Model yoksa AÇIK hata.

    Postprocess (Ultralytics çıktısı): out=[1, 4+nc, N] veya [1, N, 4+nc]; kutu (cx,cy,w,h)
    model-piksel uzayında (0..imgsz), objectness YOK (v8/v11) → sınıf skoru = güven. NMS uygulanır.
    Detection = (cx, cy, w, h, score) TAM kare uzayında (ROI geri-ölçek + offset).
    """

    def __init__(self, model_path, roi_frac=0.7, conf=0.35, iou=0.45):
        import os
        if not model_path or not os.path.exists(model_path):
            raise FileNotFoundError(
                f"ONNX model yok: {model_path} — YOLOv8/v11 ONNX'i model_path ile verin "
                "(best.pt→ONNX: `yolo export model=best.pt format=onnx`).")
        import onnxruntime as ort
        self.sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self._inp = self.sess.get_inputs()[0].name
        shp = self.sess.get_inputs()[0].shape  # [1,3,H,W]
        self.in_h = int(shp[2]) if isinstance(shp[2], int) else INFER_H
        self.in_w = int(shp[3]) if isinstance(shp[3], int) else INFER_W
        self.roi_frac = roi_frac
        self.conf = conf
        self.iou = iou

    def detect(self, frame):
        import cv2
        crop, x0, y0 = roi_crop(frame, self.roi_frac)
        ch, cw = crop.shape[:2]
        img = cv2.resize(crop, (self.in_w, self.in_h))
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        blob = np.transpose(rgb, (2, 0, 1))[None, ...]          # 1,3,H,W
        out = self.sess.run(None, {self._inp: blob})[0]
        preds = self._decode(out)                                # (cx,cy,w,h,score) model uzayında
        sx, sy = cw / self.in_w, ch / self.in_h
        dets = []
        for cx, cy, bw, bh, sc in preds:                         # model → crop → tam kare
            dets.append((x0 + cx * sx, y0 + cy * sy, bw * sx, bh * sy, sc))
        return dets

    def _decode(self, out):
        import cv2
        a = np.squeeze(out)
        if a.ndim != 2:
            return []
        if a.shape[0] < a.shape[1]:      # (4+nc, N) → (N, 4+nc): küçük boyut kanal
            a = a.T
        boxes = a[:, :4]
        scores_all = a[:, 4:]
        if scores_all.shape[1] == 0:
            return []
        cls = np.argmax(scores_all, axis=1)
        conf = scores_all[np.arange(scores_all.shape[0]), cls]
        keep = conf >= self.conf
        boxes, conf = boxes[keep], conf[keep]
        if len(conf) == 0:
            return []
        x = boxes[:, 0] - boxes[:, 2] / 2.0                      # merkez → sol-üst (NMS için)
        y = boxes[:, 1] - boxes[:, 3] / 2.0
        rects = np.stack([x, y, boxes[:, 2], boxes[:, 3]], axis=1).tolist()
        idxs = cv2.dnn.NMSBoxes(rects, conf.tolist(), self.conf, self.iou)
        res = []
        for i in np.array(idxs).flatten() if len(idxs) > 0 else []:
            cx, cy, bw, bh = boxes[i]
            res.append((float(cx), float(cy), float(bw), float(bh), float(conf[i])))
        return res


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
                            roi_frac=kw.get("roi_frac", 0.7), conf=kw.get("conf", 0.35),
                            iou=kw.get("iou", 0.45))
    if backend == "tensorrt":
        return TensorRTDetector(kw.get("engine_path", ""))
    raise ValueError(f"bilinmeyen inference backend: {backend}")
