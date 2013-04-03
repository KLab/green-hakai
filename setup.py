try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

from ghakai import __version__

setup(name='green-hakai',
      py_modules=['ghakai'],
      scripts=['ghakai'],
      version=__version__,
      install_requires=[
          "gevent>=1.0rc2",
          "geventhttpclient",
          "PyYAML",
          ],
      description="HTTP Loadtest tool.",
      )
