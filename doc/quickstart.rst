Quick Start
===========

Minimal Scenario
-----------------

This scenario access to `http://localhost:8000/` then `http://localhost:8000/hello`

.. code-block:: yaml

    # minimal.yml
    domain: http://localhost:8000

    actions:
        - path: /
        - path: /hello

To run this scenario::

    $ ghakai minimal.yml 

    request count:2, concurrenry:1, 17.998099 req/s
    SUCCESS 2
    FAILED 0
    Average response time[ms]: 54.9119710922

Loadtest
--------

``--max-scenario`` (``-s``) specifies number of concurrent scenario execution::

    $ ghakai -s20 minimal.yml 

    request count:40, concurrenry:20, 214.787955 req/s
    SUCCESS 40
    FAILED 0
    Average response time[ms]: 55.2126586437

To use multicore, ``--fork`` (``-f``) specifies number of processes::

    $ ghakai -s20 -f2 minimal.yml 

    request count:80, concurrenry:40, 294.365526 req/s
    SUCCESS 80
    FAILED 0
    Average response time[ms]: 59.4713330269

Note that ``--max-scenario`` means concurrent scenario **per process**.
For example, 40 concurrent scenario executed on above example.

You can specify ``--max-requests`` (``-c``) to number of restrict concurrent
requests per process. For example, following command executes 40 concurrent
scenario and up to 10 oncurrent requests::

    $ ghakai -s20 -f2 -c5 minimal.yml 

    request count:80, concurrenry:10, 151.640082 req/s
    SUCCESS 80
    FAILED 0
    Average response time[ms]: 127.687591314

``--loop`` (``-s``) multiplies number of scenario execution without increase
concurrency::

    $ ghakai -n10 minimal.yml

    request count:20, concurrenry:1, 17.875097 req/s
    SUCCESS 20
    FAILED 0
    Average response time[ms]: 55.7971715927

``--total-duration`` (``-d``) limits total execution time (seconds)::

    $ ghakai -n10000 -d3 minimal.yml

    request count:60, concurrenry:1, 19.984147 req/s
    SUCCESS 60
    FAILED 0
    Average response time[ms]: 49.3332505226
