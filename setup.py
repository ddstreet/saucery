from setuptools import setup

setup(
    name='saucery',
    version='1.0.0',
    packages=['saucery'],
    install_requires=[
        'paramiko',
        'dateparser',
    ],
    scripts=['scripts/grocer', 'scripts/saucier'],
)
