"""video_streamer pipeline builder testleri (SAD §16): hw NVENC / dev x264, RTSP factory sözleşmesi."""

import pytest

from gokdogan_video_streamer import pipeline as P


def test_dev_videotestsrc_uses_x264_and_pay0():
    s = P.build_launch(mode="dev", source="videotestsrc")
    assert s.startswith("( ") and s.endswith(" )")  # RTSP factory bin
    assert "videotestsrc" in s
    assert "x264enc" in s and "nvv4l2h264enc" not in s
    assert "rtph264pay name=pay0" in s  # factory sözleşmesi


def test_hardware_uses_nvenc():
    s = P.build_launch(mode="hardware", source="v4l2", device="/dev/video0")
    assert "nvv4l2h264enc" in s and "x264enc" not in s
    assert "v4l2src device=/dev/video0" in s
    assert "rtph264pay name=pay0" in s


def test_bitrate_units_hw_is_bits_dev_is_kbits():
    hw = P.build_launch(mode="hardware", source="v4l2", bitrate_kbps=4000)
    dev = P.build_launch(mode="dev", source="videotestsrc", bitrate_kbps=4000)
    assert "bitrate=4000000" in hw  # NVENC bit/s
    assert "bitrate=4000" in dev  # x264 kbit/s


def test_resolution_and_fps_in_caps():
    s = P.build_launch(mode="dev", source="videotestsrc", width=1920, height=1200, fps=30)
    assert "width=1920" in s and "height=1200" in s and "framerate=30/1" in s


def test_hardware_rejects_videotestsrc():
    with pytest.raises(ValueError):
        P.build_launch(mode="hardware", source="videotestsrc")


def test_file_requires_location():
    with pytest.raises(ValueError):
        P.build_launch(mode="dev", source="file")
    s = P.build_launch(mode="dev", source="file", location="/tmp/x.mp4")
    assert "filesrc location=/tmp/x.mp4" in s and "decodebin" in s


def test_invalid_mode_and_source_rejected():
    with pytest.raises(ValueError):
        P.build_launch(mode="sim", source="videotestsrc")
    with pytest.raises(ValueError):
        P.build_launch(mode="dev", source="magic")


def test_rtsp_url_builder():
    assert P.rtsp_url("10.0.0.5", 8554, "gokdogan") == "rtsp://10.0.0.5:8554/gokdogan"
    assert P.rtsp_url("10.0.0.5", 8554, "/gokdogan") == "rtsp://10.0.0.5:8554/gokdogan"
