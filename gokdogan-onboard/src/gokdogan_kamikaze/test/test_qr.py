"""QR pipeline testi (SAD §12): sentetik eğik plakadaki QR → perspektif düzeltme → dual decode."""
import numpy as np
import pytest

from gokdogan_kamikaze.qr import decode_qr

TEXT = "TF-2026-A1B2"


def _make_plate(text, plate=520, angle=0.0):
    """qrcode + opencv ile eğik plakada QR (test-yerel; tools/synthetic_qr ile aynı mantık)."""
    import cv2
    import qrcode
    qr = qrcode.QRCode(box_size=10, border=4,
                       error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(text)
    qr.make(fit=True)
    arr = np.array(qr.make_image(fill_color="black", back_color="white").convert("L"),
                   dtype=np.uint8)
    canvas = np.full((plate, plate), 200, dtype=np.uint8)
    scale = int(plate * 0.6) / max(arr.shape)
    r = cv2.resize(arr, (int(arr.shape[1] * scale), int(arr.shape[0] * scale)),
                   interpolation=cv2.INTER_NEAREST)
    oy, ox = (plate - r.shape[0]) // 2, (plate - r.shape[1]) // 2
    canvas[oy:oy + r.shape[0], ox:ox + r.shape[1]] = r
    img = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    if abs(angle) > 1e-3:
        k = np.tan(np.radians(angle)) * plate * 0.25
        src = np.float32([[0, 0], [plate, 0], [plate, plate], [0, plate]])
        dst = np.float32([[k, 0], [plate - k, 0], [plate, plate], [0, plate]])
        m = cv2.getPerspectiveTransform(src, dst)
        img = cv2.warpPerspective(img, m, (plate, plate), borderValue=(180, 180, 180))
    return img


def test_decode_frontal():
    assert decode_qr(_make_plate(TEXT, angle=0.0)) == TEXT


@pytest.mark.parametrize("angle", [15.0, 25.0])
def test_decode_skewed(angle):
    """Eğik (oblik) plaka → pipeline perspektifi düzeltip okumalı."""
    assert decode_qr(_make_plate(TEXT, angle=angle)) == TEXT


def test_no_qr_returns_none():
    blank = np.full((400, 400, 3), 128, dtype=np.uint8)
    assert decode_qr(blank) is None
