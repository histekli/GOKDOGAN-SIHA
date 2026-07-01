from setuptools import find_packages, setup
package_name = "gokdogan_hss"
setup(
    name=package_name, version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"])],
    install_requires=["setuptools"], zip_safe=True,
    maintainer="GOKDOGAN Team", maintainer_email="hasancan9091@gmail.com",
    description="GÖKDOĞAN HSS kaçınma (APF+Dubins)", license="Proprietary",
    tests_require=["pytest"],
    entry_points={"console_scripts": ["hss_node = gokdogan_hss.hss_node:main"]})
