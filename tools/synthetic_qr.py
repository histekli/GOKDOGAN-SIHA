"""Sentetik QR üretimi (SAD §20 sim): eğik plakadaki QR kareleri — kamikaze QR pipeline testi.

qrcode ile QR üret, plakaya yerleştir, perspektif eğ (dalış açısını taklit). decode_qr ile doğrulanır.
"""
import numpy as np


def make_qr(text, box=8, border=4):
    """QR görüntüsü (grayscale uint8, siyah/beyaz)."""
    import qrcode
    qr = qrcode.QRCode(box_size=box, border=border,
                       error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("L")
    return np.array(img, dtype=np.uint8)


def make_plate(text, plate=480, angle=0.0):
    """QR'ı gri plakaya yerleştir + perspektif eğ (angle derece ~ dalış eğikliği). BGR döndürür."""
    import cv2
    qr = make_qr(text)
    canvas = np.full((plate, plate), 200, dtype=np.uint8)   # açık gri plaka
    qh, qw = qr.shape
    scale = int(plate * 0.6) / max(qh, qw)
    qr_r = cv2.resize(qr, (int(qw * scale), int(qh * scale)), interpolation=cv2.INTER_NEAREST)
    rh, rw = qr_r.shape
    oy, ox = (plate - rh) // 2, (plate - rw) // 2
    canvas[oy:oy + rh, ox:ox + rw] = qr_r
    img = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    if abs(angle) > 1e-3:
        # Üst kenarı içeri çekerek perspektif (oblik bakış)
        k = np.tan(np.radians(angle)) * plate * 0.25
        src = np.float32([[0, 0], [plate, 0], [plate, plate], [0, plate]])
        dst = np.float32([[k, 0], [plate - k, 0], [plate, plate], [0, plate]])
        m = cv2.getPerspectiveTransform(src, dst)
        img = cv2.warpPerspective(img, m, (plate, plate), borderValue=(180, 180, 180))
    return img
