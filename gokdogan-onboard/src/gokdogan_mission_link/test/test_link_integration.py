"""mission_link entegrasyon testi (SITL'siz, tek rclpy context → cross-process DDS yok).

Doğrular (Kabul Kapısı 2): çift-yön akış (aircraft_vision↑ UDP, operator_cmd/server_data↓ TCP),
heartbeat, TCP kopma→onboard devam+reconnect. Kilit/kamikaze gerçek FSM ile Faz 4/5'te.
"""
import socket
import threading
import time

import pytest
import rclpy
from rclpy.executors import MultiThreadedExecutor

from gokdogan_msgs.msg import MissionCommand, Opponents
from gokdogan_common import qos
from gokdogan_mission_link import protocol as P
from gokdogan_mission_link.mission_link_node import MissionLinkNode


@pytest.fixture
def link():
    rclpy.init()
    node = MissionLinkNode()
    got = {"cmd": [], "opp": []}
    probe = rclpy.create_node("test_probe")
    probe.create_subscription(MissionCommand, "/mission/command",
                              lambda m: got["cmd"].append(m), qos.mission_command())
    probe.create_subscription(Opponents, "/server/opponents",
                              lambda m: got["opp"].append(m), qos.server_data())
    ex = MultiThreadedExecutor()
    ex.add_node(node)
    ex.add_node(probe)
    th = threading.Thread(target=ex.spin, daemon=True)
    th.start()
    time.sleep(1.0)  # soketler + timerlar ayağa kalksın
    try:
        yield node, got
    finally:
        node.shutdown()
        ex.shutdown()
        node.destroy_node()
        probe.destroy_node()
        rclpy.shutdown()


def _connect_gcs():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.bind(("0.0.0.0", P.UDP_PORT))
    udp.settimeout(2.0)
    tcp = socket.create_connection(("127.0.0.1", P.TCP_PORT), timeout=3.0)
    return udp, tcp


def _seq():
    n = 0
    while True:
        n += 1
        yield n


def test_bidirectional_and_reconnect(link):
    node, got = link
    udp, tcp = _connect_gcs()
    seq = _seq()
    # GCS heartbeat + operator_cmd START_LOCK gönder
    tcp.sendall(P.frame_tcp(P.build("heartbeat", next(seq), role="gcs")))
    tcp.sendall(P.frame_tcp(P.build("operator_cmd", next(seq), cmd="START_LOCK")))
    # server_data gönder
    tcp.sendall(P.frame_tcp(P.build("server_data", next(seq),
                opponents=[{"takim_no": 42, "enlem": 39.9, "boylam": 32.8}], hss=[])))

    # ↑ UDP aircraft_vision al (fsm_state içermeli)
    got_vision = False
    for _ in range(20):
        try:
            data, _ = udp.recvfrom(65535)
        except socket.timeout:
            break
        m = P.decode(data)
        if m.get("type") == "aircraft_vision" and "fsm_state" in m:
            got_vision = True
            break
    assert got_vision, "aircraft_vision UDP alınamadı"

    # ↓ operator_cmd → /mission/command yayınlandı mı
    deadline = time.time() + 3
    while time.time() < deadline and not got["cmd"]:
        time.sleep(0.1)
    assert got["cmd"], "/mission/command yayınlanmadı"
    assert got["cmd"][0].type == MissionCommand.START_LOCK

    # ↓ server_data → /server/opponents
    deadline = time.time() + 3
    while time.time() < deadline and not got["opp"]:
        time.sleep(0.1)
    assert got["opp"] and got["opp"][0].opponents[0].takim_no == 42

    # TCP kopma → onboard devam etmeli (node hâlâ canlı) + reconnect
    tcp.close()
    time.sleep(1.5)
    got["cmd"].clear()
    tcp2 = socket.create_connection(("127.0.0.1", P.TCP_PORT), timeout=3.0)
    tcp2.sendall(P.frame_tcp(P.build("operator_cmd", next(seq), cmd="ABORT")))
    deadline = time.time() + 3
    while time.time() < deadline and not got["cmd"]:
        time.sleep(0.1)
    assert got["cmd"], "reconnect sonrası /mission/command yayınlanmadı (onboard kopmada öldü mü?)"
    assert got["cmd"][0].type == MissionCommand.ABORT
    tcp2.close()
    udp.close()
