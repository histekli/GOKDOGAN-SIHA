"""mission_link protocol birim testleri (SAD §9): çerçeveleme + bozuk/partial dayanıklılık."""
import os
import random
import struct

from gokdogan_mission_link import protocol as P


def test_encode_decode_roundtrip():
    msg = P.build("operator_cmd", 7, cmd="START_LOCK", target_id=3)
    out = P.decode(P.encode(msg))
    assert out["type"] == "operator_cmd" and out["seq"] == 7 and out["cmd"] == "START_LOCK"


def test_envelope_validation():
    assert P.is_valid_envelope(P.build("heartbeat", 1, role="gcs"))
    assert not P.is_valid_envelope({"type": "heartbeat"})            # seq/ts yok
    assert not P.is_valid_envelope({"type": "bogus", "seq": 1, "ts": 0.0})  # bilinmeyen tür


def test_tcp_framer_single_and_multiple():
    f = P.TcpFramer()
    a = P.frame_tcp(P.build("heartbeat", 1, role="gcs"))
    b = P.frame_tcp(P.build("operator_cmd", 2, cmd="ABORT"))
    msgs = f.feed(a + b)
    assert [m["type"] for m in msgs] == ["heartbeat", "operator_cmd"]


def test_tcp_framer_split_frame():
    f = P.TcpFramer()
    frame = P.frame_tcp(P.build("config", 5, autonomy_weights={"mesafe": 0.4}))
    # Baytları ikiye böl — partial feed çökmemeli
    assert f.feed(frame[:3]) == []
    assert f.feed(frame[3:7]) == []
    out = f.feed(frame[7:])
    assert len(out) == 1 and out[0]["type"] == "config"


def test_tcp_framer_corrupt_length_no_crash():
    errors = []
    f = P.TcpFramer(on_error=lambda m: errors.append(m))
    # Devasa uzunluk (bozuk) → buffer sıfırlanır, çökme yok, hata loglanır (stream desync)
    bad = struct.pack(">I", P.MAX_FRAME + 1) + b"\x00\x00"
    out = f.feed(bad)
    assert out == [] and errors  # çökme yok + hata loglandı
    # Sıfırlama sonrası taze geçerli frame normal parse edilir
    out2 = f.feed(P.frame_tcp(P.build("heartbeat", 9, role="onboard")))
    assert [m["type"] for m in out2] == ["heartbeat"]


def test_tcp_framer_garbage_body_skipped():
    f = P.TcpFramer()
    garbage = struct.pack(">I", 5) + b"\xff\xff\xff\xff\xff"  # geçerli uzunluk, bozuk msgpack
    good = P.frame_tcp(P.build("heartbeat", 1, role="gcs"))
    out = f.feed(garbage + good)
    assert [m["type"] for m in out] == ["heartbeat"]  # bozuk atlandı, iyi geçti


def test_1000_packets_loss_disorder_no_crash():
    """1000 paket: rastgele bozulma/bölme/atlama altında çökme yok (prompt §5)."""
    random.seed(1234)
    f = P.TcpFramer()
    recovered = 0
    for i in range(1000):
        frame = P.frame_tcp(P.build("aircraft_vision", i, is_locked=False, fsm_state=2))
        r = random.random()
        if r < 0.15:
            continue  # paket kaybı — atla
        elif r < 0.25:
            frame = frame[: len(frame) // 2]  # yarım (partial) — çökmemeli
        elif r < 0.35:
            frame = os.urandom(len(frame))    # tam çöp — çökmemeli
        out = f.feed(frame)
        recovered += len(out)
    # Sağlam paketlerin bir kısmı kurtarıldı ve HİÇ istisna atılmadı
    assert recovered > 0


def test_udp_decode_garbage_no_crash():
    for _ in range(1000):
        try:
            P.decode(os.urandom(random.randint(0, 64)))
        except ValueError:
            pass  # beklenen — çökme yok
