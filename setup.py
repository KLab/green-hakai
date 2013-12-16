#!/usr/bin/env python
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

from greenload import __version__

setup(name='greenload',
      version=__version__,
      packages=['greenload'],
      scripts=['ghakai'],
      install_requires=[
          "gevent",
          "geventhttpclient",
          "PyYAML",
          ],
      description="HTTP Loadtest tool.",
      )
