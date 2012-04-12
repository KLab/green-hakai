#!/usr/bin/env python
# coding: utf-8
u"""インターネット破壊の gevent 版.

Ruby の internethakai より機能は少ないですが、 Ruby と gem のセットアップ
がすぐにできないときはこっちのほうが楽.

    easy_install https://bitbucket.org/denis/gevent/get/tip.tar.gz
    easy_install https://github.com/gwik/geventhttpclient/tarball/master
    easy_install PyYaml
"""
from __future__ import print_function, division

from geventhttpclient import HTTPClient, URL

import sys
import logging
import urllib, urllib2
import urlparse
import time
import gevent.pool
import random

logger = logging.getLogger(__name__)

def load_conf(filename):
    import yaml
    return yaml.load(open(filename))

def load_vars(conf):
    V = {}
    if 'vars' not in conf:
        return V
    for var in conf['vars']:
        var_name = var['var_name']
        var_file = var['var_file']
        vlist = open(var_file).read().splitlines()
        V[var_name] = vlist
    return V

def select_vars(VARS):
    U = {}
    for k,v in VARS.iteritems():
        U[k] = random.choice(v)
    return U


def hakai(client, conf, V):
    global SUCC, FAIL

    actions = conf['actions']

    for _ in xrange(NLOOP):
        U = select_vars(V)

        for action in actions:
            path = action['path']
            for k,v in U.iteritems():
                path = path.replace("%("+k+")%", v)

            if '?' in path:
                p1, p2 = path.split('?')
                p2 = urlparse.parse_qsl(p2)
                p2 = urllib.urlencode(p2)
                path = p1 + '?' + p2
            t = time.time()
            response = client.get(path)
            response.read()
            t = time.time() - t
            if response.status_code == 200:
                SUCC += 1
                sys.stderr.write('o')
                #print(t*1000, response.status_code, path)
            else:
                FAIL += 1
                sys.stderr.write('x')
                #print(response, response.status_code)

def main():
    global NLOOP, SUCC, FAIL
    C1 = 1
    C2 = 1
    NLOOP = 1
    SUCC = 0
    FAIL = 0

    import sys
    conf = load_conf(sys.argv[1])

    loglevel = int(conf.get("log_level"))*10
    logger.setLevel(loglevel)

    vars_ = load_vars(conf)

    C1 = int(conf.get('concurrency', 1))
    C2 = int(conf.get('max_scenario', C1))
    NLOOP = int(conf.get('loop', 1))
    TOTAL_DURATION = float(conf.get('total_duration', None))
    USER_AGENT = conf.get('user_agent', 'ghakai')

    timeout = float(conf.get('timeout', 10))
    host = conf['domain']
    headers = {'User-Agent': USER_AGENT}
    client = HTTPClient.from_url(host, concurrency=C1,
                                 connection_timeout=timeout,
                                 network_timeout=timeout,
                                 headers=headers,
                                 )

    group = gevent.pool.Pool(size=C2)
    now = time.time()
    for _ in xrange(C2):
        group.spawn(hakai, client, conf, vars_)
    group.join(TOTAL_DURATION)
    group.kill()
    delta = time.time() - now

    NREQ = SUCC+FAIL
    req_per_sec = NREQ / delta
    print("request count:%d, concurrenry:%d, %f req/s" % (NREQ, C1, req_per_sec))
    print("SUCCESS", SUCC)
    print("FAILED", FAIL)

if __name__ == '__main__':
    main()
