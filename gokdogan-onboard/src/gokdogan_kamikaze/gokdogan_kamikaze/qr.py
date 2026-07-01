"""QR okuma pipeline (SAD §12, KESIN_PLAN §7): grayscale→CLAHE→adaptive threshold→4 köşe→
perspektif düzeltme (warpPerspective)→OpenCV QRCodeDetector + pyzbar DUAL decode.

Eğik plakadaki QR'ı (kamikaze dalışında) düzeltip okur. Saf OpenCV/pyzbar — test edilebilir.
"""
import cv2
import numpy as np


def _to_gray(image):
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def preprocess(gray):
    """CLAHE (kontrast) + adaptive threshold (aydınlatmaya dayanıklı ikili görüntü)."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g = clahe.apply(gray)
    return cv2.adaptiveThreshold(
        g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 5)


def _order_corners(pts):
    """4 köşeyi TL,TR,BR,BL sırasına diz."""
    pts = pts.astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([
        pts[np.argmin(s)],   # TL
        pts[np.argmin(d)],   # TR
        pts[np.argmax(s)],   # BR
        pts[np.argmax(d)],   # BL
    ], dtype=np.float32)


def find_quad(binary, min_area_frac=0.02):
    """En büyük 4-köşeli konturu (plaka) bul."""
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    h, w = binary.shape[:2]
    min_area = min_area_frac * h * w
    best, best_area = None, min_area
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            a = cv2.contourArea(approx)
            if a > best_area:
                best, best_area = approx, a
    return best


def warp(gray, quad, size=320):
    src = _order_corners(quad.reshape(4, 2))
    dst = np.array([[0, 0], [size, 0], [size, size], [0, size]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(gray, m, (size, size))


def dual_decode(img):
    """pyzbar + OpenCV QRCodeDetector ile çift decode (biri okursa döner)."""
    try:
        from pyzbar import pyzbar
        for obj in pyzbar.decode(img):
            if obj.type == "QRCODE":
                return obj.data.decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        pass
    try:
        det = cv2.QRCodeDetector()
        text, _, _ = det.detectAndDecode(img)
        if text:
            return text
    except Exception:  # noqa: BLE001
        pass
    return None


def decode_qr(image):
    """Eğik plakadaki QR'ı oku. Bulunamazsa None (kamikaze min-alt pull-up'a düşer)."""
    gray = _to_gray(image)
    # 1) Doğrudan dene (pyzbar hafif eğime dayanıklı)
    t = dual_decode(gray)
    if t:
        return t
    # 2) Perspektif düzeltme sonrası dene
    binary = preprocess(gray)
    quad = find_quad(binary)
    if quad is not None:
        w = warp(gray, quad)
        t = dual_decode(w) or dual_decode(preprocess(w))
        if t:
            return t
    # 3) Son çare: ikili görüntüde dene
    return dual_decode(binary)
