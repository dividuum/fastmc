from setuptools import setup

setup(
    name = 'fastmc',
    version = '0.6',
    description = 'Fast Minecraft Protocol Parser/Writer',
    author = 'Florian Wesch',
    author_email = 'fw@dividuum.de',
    packages = ['fastmc'],
    license = 'BSD2',
    install_requires = ['requests', 'pycrypto', 'simplejson'],
    zip_safe = True,
)
