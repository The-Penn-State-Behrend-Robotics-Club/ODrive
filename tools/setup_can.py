from setuptools import setup

setup(
    name="odrive_can",
    packages=["odrive_can", "odrive_can.async_reader"],
    version="0.0.1",
    description="Connects to ODrives using the CAN bus",
    author="Alan Everett",
    author_email="thatcomputerguy0101@gmail.com",
    license="TODO: Find a license",
    url="https://github.com/odriverobotics/ODrive",  # Main ODrive site, not yet including odrive_can
    keywords=["odrive", "motor", "motor control", "can", "can bus"],
    install_requires=[
        "ipython",  # Used to do the interactive parts of the module prompt (currently not implemented)
        "can",  # Used to communicate to the ODrives
        "cantools",  # Used to parse the CAN database
    ],
    classifiers=[],
    package_data={'': [
        'odrive-cansimple.dbc',
    ]},
    include_package_data=True,
    zip_safe=False,
)
