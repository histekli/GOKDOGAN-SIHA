"""GÖKDOĞAN competition bringup (SAD §5/§8/§20).

  ros2 launch gokdogan_bringup competition.launch.py mode:=sitl
  ros2 launch gokdogan_bringup competition.launch.py mode:=hardware   # ⚠️ ON-DEVICE

mode → config/{sitl,hardware}.yaml + MAVROS fcu_url. Otonomi node'ları SITL/gerçek
ayrımını bilmez (İ5) — yalnız fcu_url değişir. DDS lokal (ROS_LOCALHOST_ONLY=1, İ4).
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _setup(context, *args, **kwargs):
    mode = LaunchConfiguration("mode").perform(context)
    if mode not in ("sitl", "hardware"):
        raise RuntimeError(f"mode 'sitl' veya 'hardware' olmalı, verilen: {mode}")

    share = get_package_share_directory("gokdogan_bringup")
    cfg = os.path.join(share, "config", f"{mode}.yaml")

    fcu_url = LaunchConfiguration("fcu_url").perform(context)
    if not fcu_url:
        fcu_url = "tcp://127.0.0.1:5760" if mode == "sitl" else "/dev/ttyTHS1:921600"

    # NOT: mavros'a YAML config dosyası verilmiyor — yalnız inline paramlar (diag ile
    # doğrulanmış çalışan biçim). Config dosyası verilince command-plugin servisleri
    # (/mavros/cmd/arming) keşfedilemez oluyordu.
    mavros = Node(
        package="mavros", executable="mavros_node", output="screen",
        parameters=[{
            "fcu_url": fcu_url,
            "tgt_system": 1,
            "tgt_component": 1,
            "system_id": 255,
            "component_id": 240,
        }],
    )

    mission_fsm = Node(
        package="gokdogan_mission_fsm", executable="mission_fsm_node",
        name="mission_fsm", output="screen", parameters=[cfg],
    )

    mission_link = Node(
        package="gokdogan_mission_link", executable="mission_link_node",
        name="mission_link", output="screen", parameters=[cfg],
    )

    nodes = [mavros, mission_fsm, mission_link]
    if LaunchConfiguration("enable_aircraft_state").perform(context) == "true":
        nodes.append(Node(
            package="gokdogan_mavlink_iface", executable="aircraft_state_node",
            name="aircraft_state", output="screen", parameters=[cfg],
        ))
    if LaunchConfiguration("enable_guidance").perform(context) == "true":
        nodes.append(Node(
            package="gokdogan_target_selector", executable="target_selector_node",
            name="target_selector", output="screen", parameters=[cfg],
        ))
        nodes.append(Node(
            package="gokdogan_guidance", executable="guidance_node",
            name="guidance", output="screen", parameters=[cfg],
        ))
    if LaunchConfiguration("enable_hss").perform(context) == "true":
        nodes.append(Node(
            package="gokdogan_hss", executable="hss_node",
            name="hss", output="screen", parameters=[cfg],
        ))
    if LaunchConfiguration("enable_kamikaze").perform(context) == "true":
        nodes.append(Node(
            package="gokdogan_kamikaze", executable="kamikaze_node",
            name="kamikaze", output="screen", parameters=[cfg],
        ))
    if LaunchConfiguration("enable_video").perform(context) == "true":
        nodes.append(Node(
            package="gokdogan_video_streamer", executable="video_streamer_node",
            name="video_streamer", output="screen", parameters=[cfg],
        ))
    return nodes


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("mode", default_value="sitl",
                              description="sitl | hardware"),
        DeclareLaunchArgument("fcu_url", default_value="",
                              description="MAVROS FCU URL (boş → mode'a göre varsayılan)"),
        DeclareLaunchArgument("enable_aircraft_state", default_value="true",
                              description="aircraft_state node'unu başlat"),
        DeclareLaunchArgument("enable_guidance", default_value="true",
                              description="target_selector + guidance node'larını başlat"),
        DeclareLaunchArgument("enable_hss", default_value="true",
                              description="hss (APF kaçınma) node'unu başlat"),
        DeclareLaunchArgument("enable_kamikaze", default_value="true",
                              description="kamikaze action node'unu başlat"),
        DeclareLaunchArgument("enable_video", default_value="false",
                              description="video_streamer (RTSP) node'unu başlat"),
        OpaqueFunction(function=_setup),
    ])
