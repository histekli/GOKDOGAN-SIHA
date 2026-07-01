"""GÖKDOĞAN mission_link wire protokolü (SAD §9, contracts/mission_link.schema.json).

Dil-bağımsız MessagePack. TCP = 4B big-endian uzunluk öneki + gövde; UDP = tek datagram.
Zarf: type, seq, ts. Bozuk/partial frame ASLA çökmez → drop + log (prompt §5).
"""
import struct
import time

import msgpack

# Kanal portları (SAD §9)
UDP_PORT = 5005      # aircraft_vision akışı (onboard→GCS), latest-wins
TCP_PORT = 5006      # kontrol (olay/komut), güvenilir + sıralı

# Bilinen mesaj türleri (contracts/mission_link.schema.json ile birebir)
UP_TYPES = {"aircraft_vision", "lock_valid", "kamikaze_result"}
DOWN_TYPES = {"operator_cmd", "server_data", "config"}
COMMON_TYPES = {"heartbeat"}
KNOWN_TYPES = UP_TYPES | DOWN_TYPES | COMMON_TYPES

MAX_FRAME = 1 << 20  # 1 MiB — üstü bozuk kabul edilir (DoS/desync koruması)


def now_ts() -> float:
    return time.time()


def build(msg_type: str, seq: int, **body) -> dict:
    """Zarflı mesaj sözlüğü üret (type, seq, ts + gövde)."""
    msg = {"type": msg_type, "seq": int(seq), "ts": now_ts()}
    msg.update(body)
    return msg


def encode(msg: dict) -> bytes:
    """Sözlük → MessagePack bytes (UDP datagramı olarak da kullanılır)."""
    return msgpack.packb(msg, use_bin_type=True)


def decode(data: bytes) -> dict:
    """MessagePack bytes → sözlük. Bozuksa ValueError atar (çökme yok, çağıran yakalar)."""
    try:
        obj = msgpack.unpackb(data, raw=False)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"msgpack decode hatası: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("mesaj sözlük değil")
    return obj


def frame_tcp(msg: dict) -> bytes:
    """TCP çerçevesi: 4B BE uzunluk + MessagePack gövde."""
    payload = encode(msg)
    return struct.pack(">I", len(payload)) + payload


def is_valid_envelope(msg: dict) -> bool:
    """Zarf alanları (type/seq/ts) var ve tür biliniyor mu."""
    return (
        isinstance(msg, dict)
        and msg.get("type") in KNOWN_TYPES
        and isinstance(msg.get("seq"), int)
        and isinstance(msg.get("ts"), (int, float))
    )


class TcpFramer:
    """TCP akışını length-prefixed mesajlara böler. Partial/bozuk frame dayanıklı.

    feed(bytes) → tam & geçerli mesajların listesi. Bozuk uzunluk → buffer sıfırlanır (resync).
    """

    def __init__(self, on_error=None):
        self._buf = bytearray()
        self._on_error = on_error or (lambda msg: None)

    def feed(self, data: bytes):
        out = []
        self._buf.extend(data)
        while True:
            if len(self._buf) < 4:
                break
            (length,) = struct.unpack(">I", self._buf[:4])
            if length == 0 or length > MAX_FRAME:
                # Bozuk/senkronsuz uzunluk = TCP stream desync (msgpack'te sync-marker yok →
                # güvenilir resync imkânsız). Buffer sıfırla; çağıran bağlantıyı resetlemeli.
                self._on_error(f"geçersiz frame uzunluğu {length} — buffer sıfırlandı (resync)")
                self._buf.clear()
                break
            if len(self._buf) < 4 + length:
                break  # partial — daha fazla veri bekle
            payload = bytes(self._buf[4:4 + length])
            del self._buf[:4 + length]
            try:
                msg = decode(payload)
            except ValueError as e:
                self._on_error(f"bozuk gövde atlandı: {e}")
                continue
            if not is_valid_envelope(msg):
                self._on_error(f"geçersiz zarf/bilinmeyen tür atlandı: {msg.get('type')}")
                continue
            out.append(msg)
        return out


class SchemaValidator:
    """contracts/mission_link.schema.json ile doğrulama (opsiyonel). Şema yoksa devre dışı."""

    def __init__(self, schema_path=None):
        self._validator = None
        if schema_path:
            try:
                import json
                import pathlib
                from jsonschema import Draft202012Validator
                schema = json.loads(pathlib.Path(schema_path).read_text(encoding="utf-8"))
                self._validator = Draft202012Validator(schema)
            except Exception:  # noqa: BLE001
                self._validator = None

    @property
    def enabled(self):
        return self._validator is not None

    def check(self, msg: dict):
        """(ok, error_str) döndürür. Şema yoksa (True, None)."""
        if self._validator is None:
            return True, None
        errs = sorted(self._validator.iter_errors(msg), key=lambda e: e.path)
        if errs:
            return False, errs[0].message
        return True, None
