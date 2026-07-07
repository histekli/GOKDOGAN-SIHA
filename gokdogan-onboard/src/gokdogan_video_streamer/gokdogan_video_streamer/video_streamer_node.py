"""video_streamer düğümü (SAD §16): ham kamerayı RTSP olarak yayınlar (overlay GCS'te).

- Pipeline `pipeline.build_launch()` ile kurulur (hardware NVENC / dev x264).
- GstRtspServer varsa RTSP sunucusu açılır; kaynak/enkoder başlatılamazsa **retry** (backoff) +
  başlatana kadar `/video/status`=STARTING/DEGRADED (placeholder). GStreamer yoksa node çökmez,
  DEGRADED durur (İ2: video yokluğu uçuşu durdurmaz).
- `/video/status` (std_msgs/String, latched) → watchdog/GCS gözlem.
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from gokdogan_common import qos
from gokdogan_video_streamer import pipeline as P


class VideoStreamerNode(Node):
    def __init__(self):
        super().__init__("video_streamer")
        self.declare_parameter("mode", "dev")  # dev | hardware
        self.declare_parameter("source", "videotestsrc")  # videotestsrc|v4l2|file|gazebo
        self.declare_parameter("device", "/dev/video0")
        self.declare_parameter("location", "")  # file kaynağı için
        self.declare_parameter("width", P.DEFAULT_WIDTH)
        self.declare_parameter("height", P.DEFAULT_HEIGHT)
        self.declare_parameter("fps", P.DEFAULT_FPS)
        self.declare_parameter("bitrate_kbps", 4000)
        self.declare_parameter("rtsp_host", "0.0.0.0")
        self.declare_parameter("rtsp_port", 8554)
        self.declare_parameter("rtsp_mount", "/gokdogan")
        self.declare_parameter("retry_backoff_s", 2.0)

        g = lambda k: self.get_parameter(k).value  # noqa: E731
        try:
            self._launch = P.build_launch(
                mode=g("mode"),
                source=g("source"),
                width=int(g("width")),
                height=int(g("height")),
                fps=int(g("fps")),
                bitrate_kbps=int(g("bitrate_kbps")),
                device=g("device"),
                location=(g("location") or None),
            )
        except ValueError as e:
            self.get_logger().error(f"geçersiz pipeline konfigürasyonu: {e}")
            self._launch = None

        self._url = P.rtsp_url(
            g("rtsp_host") if g("rtsp_host") != "0.0.0.0" else "127.0.0.1", g("rtsp_port"), g("rtsp_mount")
        )
        self._status_pub = self.create_publisher(String, "/video/status", qos.mission_mode())
        self._server = None
        self._loop = None
        self._started = False
        self._backoff = float(g("retry_backoff_s"))
        self._publish_status("INIT")
        # başlatmayı timer'a bırak (executor spin'i bloklamadan retry)
        self._retry_timer = self.create_timer(0.1, self._try_start)

    def _publish_status(self, state, detail=""):
        msg = String()
        msg.data = f"{state} url={self._url}" + (f" {detail}" if detail else "")
        self._status_pub.publish(msg)
        self.get_logger().info(f"video_streamer: {msg.data}")

    def _try_start(self):
        # tek sefer başarı → timer'ı yavaşlat (heartbeat), aksi halde backoff ile tekrar dene
        self._retry_timer.cancel()
        if self._launch is None:
            self._publish_status("DEGRADED", "pipeline konfig hatası")
            self._retry_timer = self.create_timer(self._backoff, self._try_start)
            return
        ok, detail = self._start_rtsp()
        if ok:
            self._started = True
            self._publish_status("STREAMING")
            self._retry_timer = self.create_timer(5.0, self._heartbeat)
        else:
            self._publish_status("DEGRADED", detail)
            self._retry_timer = self.create_timer(self._backoff, self._try_start)

    def _heartbeat(self):
        self._publish_status("STREAMING")

    def _start_rtsp(self):
        """GstRtspServer ile RTSP başlat. Bağımlılık/kaynak yoksa (False, sebep) döner (çökmez)."""
        if self._server is not None:
            return True, ""
        try:
            import gi

            gi.require_version("Gst", "1.0")
            gi.require_version("GstRtspServer", "1.0")
            from gi.repository import Gst, GstRtspServer, GLib
        except (ImportError, ValueError) as e:
            return False, f"GStreamer/GstRtspServer yok: {e}"
        try:
            if not Gst.is_initialized():
                Gst.init(None)
            host = self.get_parameter("rtsp_host").value
            port = str(self.get_parameter("rtsp_port").value)
            mount = self.get_parameter("rtsp_mount").value

            server = GstRtspServer.RTSPServer()
            server.set_address(host)
            server.set_service(port)
            factory = GstRtspServer.RTSPMediaFactory()
            factory.set_launch(self._launch)
            factory.set_shared(True)
            server.get_mount_points().add_factory(mount if mount.startswith("/") else "/" + mount, factory)
            server.attach(None)

            self._loop = GLib.MainLoop()
            import threading

            threading.Thread(target=self._loop.run, daemon=True).start()
            self._server = server
            return True, ""
        except Exception as e:  # noqa: BLE001 — RTSP başlatma hatası node'u düşürmez
            return False, f"RTSP başlatılamadı: {e}"

    def destroy_node(self):
        if self._loop is not None:
            try:
                self._loop.quit()
            except Exception:  # noqa: BLE001
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VideoStreamerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
