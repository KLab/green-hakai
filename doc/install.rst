Install
=======

Prerequirements
----------------

ghakai requires Python 2.6 or 2.7.

CentOS::

    $ sudo yum install python-devel

Debian(Ubuntu)::

    $ sudo apt-get install python-dev


Virtualenv
-----------

Using virtualenv_ is optional but highly recommended.

.. _virtualenv: https://pypi.python.org/pypi/virtualenv

Virtualenv creates separated Python environment directory for you::

    $ ./virtualenv --distribute ~/ghakai  # replace ~/ghakai to somewhere you want to use

After setup virtualenv, you can activate the environment::

    $ source ~/ghakai/bin/activate
    (ghakai) $ which pip
    /home/methane/ghakai/bin/pip

You can also execute script in venv without activate the venv::

    $ ~/ghakai/bin/pip

Install
--------

Install required libraries::

    (ghakai) $ pip install -r requirements.txt

Install ghakai itself::

    (ghakai) $ ./setup.py install
