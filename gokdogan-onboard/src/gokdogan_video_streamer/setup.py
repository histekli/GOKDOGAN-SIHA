from setuptools import find_packages, setup

package_name = "gokdogan_video_streamer"
setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="GOKDOGAN Team",
    maintainer_email="hasancan9091@gmail.com",
    description="GÖKDOĞAN video_streamer — ham kamera RTSP yayını (GStreamer)",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={"console_scripts": ["video_streamer_node = gokdogan_video_streamer.video_streamer_node:main"]},
)
