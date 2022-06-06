from setuptools import setup

setup(
    name='saucery',
    version='1.0.0',
    packages=[
        'saucery',
        'saucery/sos',
        'saucery/reduction',
        'saucery/reduction/analysis',
        'saucery/reduction/reference',
    ],
    install_requires=[
    ],
    scripts=[
        'scripts/saucier',
        'scripts/sosreport-sftp-downloader',
    ],
)
