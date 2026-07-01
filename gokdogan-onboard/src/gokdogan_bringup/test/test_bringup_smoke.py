"""Bringup entegrasyon smoke testi (launch_testing, SITL'siz).

Doğrular: (1) stack ayağa kalkar; (2) mission_fsm ACTIVE olur ve /mission/mode IDLE yayınlar
(lifecycle + QoS mission_mode TRANSIENT_LOCAL); (3) MAVROS bağlı DEĞİLKEN TAKEOFF reddedilir
(yazılım kapısı + degraded, §5.2). Tam SITL otonom kalkış: scripts/run_sitl_stack.sh.
"""
import os
import time
import unittest

import launch
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from ament_index_python.packages import get_package_share_directory
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource

from gokdogan_msgs.msg import MissionMode
from gokdogan_msgs.srv import SetMissionMode
from gokdogan_common import qos


@pytest.mark.launch_test
def generate_test_description():
    share = get_package_share_directory("gokdogan_bringup")
    bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(share, "launch", "competition.launch.py")),
        launch_arguments={"mode": "sitl"}.items(),
    )
    return (
        launch.LaunchDescription([bringup, launch_testing.actions.ReadyToTest()]),
        {},
    )


class TestBringup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node("test_bringup")

    @classmethod
    def tearDownClass(cls):
        cls.node.destroy_node()
        rclpy.shutdown()

    def _spin(self, secs):
        t0 = time.time()
        while time.time() - t0 < secs:
            rclpy.spin_once(self.node, timeout_sec=0.1)

    def test_1_mission_mode_idle_published(self):
        got = {}

        def cb(msg):
            got["mode"] = msg

        self.node.create_subscription(MissionMode, "/mission/mode", cb, qos.mission_mode())
        t0 = time.time()
        while time.time() - t0 < 40 and "mode" not in got:
            rclpy.spin_once(self.node, timeout_sec=0.2)
        self.assertIn("mode", got, "/mission/mode hiç yayınlanmadı (mission_fsm active değil?)")
        self.assertEqual(got["mode"].state, MissionMode.IDLE, "başlangıç IDLE olmalı")
        self.assertEqual(got["mode"].active_service, MissionMode.SVC_NONE)

    def test_2_takeoff_rejected_without_fcu(self):
        cli = self.node.create_client(SetMissionMode, "/mission_fsm/set_mission_mode")
        self.assertTrue(cli.wait_for_service(timeout_sec=20), "set_mission_mode servisi yok")
        req = SetMissionMode.Request()
        req.mode = MissionMode.TAKEOFF
        fut = cli.call_async(req)
        rclpy.spin_until_future_complete(self.node, fut, timeout_sec=15)
        res = fut.result()
        self.assertIsNotNone(res, "servis yanıt vermedi")
        # MAVROS bağlı değil (SITL yok) → TAKEOFF reddedilmeli
        self.assertFalse(res.success, "bağlantısızken TAKEOFF reddedilmeliydi")


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):
    def test_exit_codes(self, proc_info):
        # mavros/node'lar SIGINT ile kapanır; -2/-15 normal
        launch_testing.asserts.assertExitCodes(
            proc_info, allowable_exit_codes=[0, -2, -15, 130])
