try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

from ghakai import __version__

setup(name='green-hakai',
      py_modules=['ghakai'],
      scripts=['ghakai'],
      version='0.1',
      install_requires=[
          "gevent>=1.0b4",
          "geventhttpclient",
          "PyYAML",
          ],
      description="HTTP Loadtest tool.",
      )
