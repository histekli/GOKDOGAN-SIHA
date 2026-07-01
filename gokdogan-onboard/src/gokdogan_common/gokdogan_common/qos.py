"""GÖKDOĞAN — Merkezî QoS profilleri (Python / rclpy). SAD §6.

KIRMIZI ÇİZGİ (prompt §2.5): Tüm publisher/subscriber AYNI adlandırılmış profili kullanır.
Humble'da pub/sub QoS uyumsuzluğu SESSİZ bağlantı kopması yapar. C++ karşılığı: qos.hpp
(birebir aynı değerler — test/test_qos.py ile parite doğrulanır).
"""
from rclpy.qos import (
    QoSProfile,
    QoSReliabilityPolicy,
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
)

_KEEP_LAST = QoSHistoryPolicy.KEEP_LAST
_BEST_EFFORT = QoSReliabilityPolicy.BEST_EFFORT
_RELIABLE = QoSReliabilityPolicy.RELIABLE
_VOLATILE = QoSDurabilityPolicy.VOLATILE
_TRANSIENT = QoSDurabilityPolicy.TRANSIENT_LOCAL


def sensor_stream() -> QoSProfile:
    """Yüksek-hız akış: en taze kazanır. /camera/image, /perception/tracks,
    /perception/selected_bbox, /mavros/setpoint_raw/attitude, /aircraft/state."""
    return QoSProfile(history=_KEEP_LAST, depth=1,
                      reliability=_BEST_EFFORT, durability=_VOLATILE)


def detections() -> QoSProfile:
    """YOLO tespitleri. /perception/detections."""
    return QoSProfile(history=_KEEP_LAST, depth=5,
                      reliability=_RELIABLE, durability=_VOLATILE)


def target_selected() -> QoSProfile:
    """Seçilen hedef (geç-katılan son değeri görmeli). /target/selected."""
    return QoSProfile(history=_KEEP_LAST, depth=10,
                      reliability=_RELIABLE, durability=_TRANSIENT)


def lock_event() -> QoSProfile:
    """Kilit olayı. /lock/event."""
    return QoSProfile(history=_KEEP_LAST, depth=20,
                      reliability=_RELIABLE, durability=_VOLATILE)


def mission_mode() -> QoSProfile:
    """Görev modu (geç-katılan son değeri görmeli). /mission/mode."""
    return QoSProfile(history=_KEEP_LAST, depth=10,
                      reliability=_RELIABLE, durability=_TRANSIENT)


def mission_command() -> QoSProfile:
    """Operatör komutu. /mission/command."""
    return QoSProfile(history=_KEEP_LAST, depth=10,
                      reliability=_RELIABLE, durability=_VOLATILE)


def server_data() -> QoSProfile:
    """Sunucu verisi (rakip/HSS). /server/opponents, /server/hss."""
    return QoSProfile(history=_KEEP_LAST, depth=5,
                      reliability=_RELIABLE, durability=_TRANSIENT)


# İsimle erişim (mission_link/fsm gibi node'lar için)
PROFILES = {
    "sensor_stream": sensor_stream,
    "detections": detections,
    "target_selected": target_selected,
    "lock_event": lock_event,
    "mission_mode": mission_mode,
    "mission_command": mission_command,
    "server_data": server_data,
}
