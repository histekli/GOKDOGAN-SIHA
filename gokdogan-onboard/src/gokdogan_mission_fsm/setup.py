from setuptools import find_packages, setup

package_name = "gokdogan_mission_fsm"

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
    description="GÖKDOĞAN Görev FSM (lifecycle) — DFA orkestratör, MAVROS tek-yazıcı.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "mission_fsm_node = gokdogan_mission_fsm.mission_fsm_node:main",
        ],
    },
)
