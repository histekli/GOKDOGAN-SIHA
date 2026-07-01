"""QoS profil tutarlılık testi (SAD §6). Golden değerler bağımsız olarak burada tanımlı;
qos.py sapmaları yakalanır. Bu ayrıca C++ (qos.hpp) parite kontratıdır — aynı golden
değerler test_qos.cpp'de doğrulanır (pub/sub sessiz kopmasını önler, prompt §2.5)."""
from rclpy.qos import (
    QoSReliabilityPolicy,
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
)

from gokdogan_common import qos

R_BE = QoSReliabilityPolicy.BEST_EFFORT
R_R = QoSReliabilityPolicy.RELIABLE
D_V = QoSDurabilityPolicy.VOLATILE
D_T = QoSDurabilityPolicy.TRANSIENT_LOCAL
H_KL = QoSHistoryPolicy.KEEP_LAST

# SAD §6 QoS matrisi — (reliability, durability, depth)
GOLDEN = {
    "sensor_stream":   (R_BE, D_V, 1),
    "detections":      (R_R,  D_V, 5),
    "target_selected": (R_R,  D_T, 10),
    "lock_event":      (R_R,  D_V, 20),
    "mission_mode":    (R_R,  D_T, 10),
    "mission_command": (R_R,  D_V, 10),
    "server_data":     (R_R,  D_T, 5),
}


def test_all_profiles_present():
    assert set(qos.PROFILES.keys()) == set(GOLDEN.keys())


def test_profiles_match_sad_golden():
    for name, (rel, dur, depth) in GOLDEN.items():
        p = qos.PROFILES[name]()
        assert p.history == H_KL, f"{name}: history KEEP_LAST değil"
        assert p.reliability == rel, f"{name}: reliability {p.reliability} != {rel}"
        assert p.durability == dur, f"{name}: durability {p.durability} != {dur}"
        assert p.depth == depth, f"{name}: depth {p.depth} != {depth}"


def test_factories_return_fresh_instances():
    # Her çağrı bağımsız profil döndürmeli (paylaşılan mutable state yok)
    a = qos.sensor_stream()
    b = qos.sensor_stream()
    assert a is not b
