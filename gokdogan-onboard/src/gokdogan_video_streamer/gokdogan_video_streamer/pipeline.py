"""GÖKDOĞAN video_streamer — GStreamer RTSP pipeline üretici (SAD §16).

Onboard **ham** kamerayı RTSP olarak yayınlar (overlay YOK — overlay+kayıt GCS'te, KTR 6.5/6.6).
Bu modül **saf**tır (GStreamer'ı import etmez) → pipeline string'i birim-test edilir.

Kaynak/encoder matrisi:
  hardware (Jetson AR0234) : v4l2src → nvvidconv → nvv4l2h264enc   (donanım HW enkoder)
  dev videotestsrc         : videotestsrc → x264enc                (masaüstü/CI, kamerasız)
  dev file                 : filesrc → decodebin → x264enc         (kayıtlı video)
  dev gazebo               : v4l2src (sanal /dev/video) → x264enc   (Gazebo kamera → v4l2loopback)

Media factory launch string DAİMA `... ! rtph264pay name=pay0 pt=96` ile biter
(GstRtspServer factory sözleşmesi).
"""

VALID_MODES = ("hardware", "dev")
VALID_SOURCES = ("videotestsrc", "v4l2", "file", "gazebo")

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1200
DEFAULT_FPS = 30  # KTR: kayıt ≥15FPS; yayın 30 hedef


def _encoder(mode, bitrate_kbps):
    """Enkoder + h264parse zinciri. hardware→NVENC, dev→x264 (zerolatency)."""
    if mode == "hardware":
        # nvv4l2h264enc bitrate bit/s ister; insert-sps-pps → RTSP re-join anında keyframe
        return f"nvv4l2h264enc bitrate={int(bitrate_kbps) * 1000} " f"insert-sps-pps=1 idrinterval=15 ! h264parse"
    # x264enc: zerolatency + sık keyframe (RTSP client geç katılırsa hızlı çözülür)
    return (
        f"x264enc tune=zerolatency speed-preset=ultrafast "
        f"bitrate={int(bitrate_kbps)} key-int-max={int(DEFAULT_FPS)} ! h264parse"
    )


def _source(source, mode, width, height, fps, device, location):
    """Kaynak + capsfilter zinciri (encoder'a beslenen ham video)."""
    caps = f"video/x-raw,width={int(width)},height={int(height)},framerate={int(fps)}/1"
    if source == "videotestsrc":
        # is-live: gerçek kamera gibi zaman damgası; pattern smpte (renkli test tablosu)
        return f"videotestsrc is-live=true pattern=smpte ! {caps}"
    if source == "file":
        if not location:
            raise ValueError("source=file için 'location' zorunlu")
        return f"filesrc location={location} ! decodebin ! videoconvert ! " f"videoscale ! {caps}"
    if source in ("v4l2", "gazebo"):
        # v4l2: gerçek USB kamera (AR0234) veya Gazebo→v4l2loopback sanal cihaz
        conv = "nvvidconv" if mode == "hardware" else "videoconvert"
        return f"v4l2src device={device} ! videoconvert ! {conv} ! {caps}"
    raise ValueError(f"bilinmeyen source: {source}")


def build_launch(
    mode="dev",
    source="videotestsrc",
    *,
    width=DEFAULT_WIDTH,
    height=DEFAULT_HEIGHT,
    fps=DEFAULT_FPS,
    bitrate_kbps=4000,
    device="/dev/video0",
    location=None,
    pt=96,
):
    """RTSP media factory için tam GStreamer launch string üretir.

    Ör (dev): "( videotestsrc ... ! x264enc ... ! h264parse ! rtph264pay name=pay0 pt=96 )"
    """
    if mode not in VALID_MODES:
        raise ValueError(f"mode ∈ {VALID_MODES}, geldi: {mode}")
    if source not in VALID_SOURCES:
        raise ValueError(f"source ∈ {VALID_SOURCES}, geldi: {source}")
    if mode == "hardware" and source == "videotestsrc":
        # donanımda test kaynağı mantıksız — kaza eseri sahada testsrc yayınlamayı engelle
        raise ValueError("hardware mode videotestsrc ile kullanılamaz (gerçek kamera bekleniyor)")

    src = _source(source, mode, width, height, fps, device, location)
    enc = _encoder(mode, bitrate_kbps)
    # RTSP factory: parantezli bin, pay0 adı zorunlu
    return f"( {src} ! videoconvert ! {enc} ! rtph264pay name=pay0 pt={int(pt)} config-interval=1 )"


def rtsp_url(host, port, mount):
    """Yayınlanan RTSP URL'i (GCS VideoPanel bunu oynatır)."""
    m = mount if mount.startswith("/") else "/" + mount
    return f"rtsp://{host}:{int(port)}{m}"
