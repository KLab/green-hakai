#!/usr/bin/env python
# coding: utf-8
u"""インターネット破壊の gevent 版.

Ruby の internethakai より機能は少ないですが、 Ruby と gem のセットアップ
がすぐにできないときはこっちのほうが楽.
"""
from __future__ import print_function, division

from geventhttpclient import HTTPClient, URL

import sys
import logging
import urllib
import urlparse
import time
import gevent.pool
import random
from collections import defaultdict

logger = logging.getLogger()


class Indicator(object):
    u"""くるくるまわる"""

    s = "|/-\\"
    def __init__(self):
        self.c = 0
        self.back = 0
    def ok(self):
        if self.back:
            sys.stdout.write('\b')
        sys.stdout.write(self.s[self.c])
        sys.stdout.flush()
        self.c = (self.c + 1) % 4
        self.back = 1
    def ng(self):
        if self.back:
            sys.stdout.write('\b')
        sys.stdout.write('x')
        sys.stdout.flush()
        self.back = 0

_indicator = Indicator()
ok = _indicator.ok
ng = _indicator.ng

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
            if STOP:
                return

            method = action.get('method', 'GET')
            org_path = path = action['path']

            for k,v in U.iteritems():
                path = path.replace("%("+k+")%", v)

            header = {}
            if method == 'POST' and 'post_param' in action:
                post_param = action['post_param']
                for k, v in post_param.items():
                    v = re.sub('%\((.+?)\)%', lambda m: U.get(m.group(1)), v)
                    post_param[k] = v
                body = urllib.urlencode(post_param)
                header['Content-Type'] = 'application/x-www-form-urlencoded'
            else:
                body = b''

            while 1:
                if '?' in path:
                    p1, p2 = path.split('?')
                    p2 = urlparse.parse_qsl(p2)
                else:
                    p1 = path
                    p2 = []

                if p2:
                    p2 = urllib.urlencode(p2)
                    path = p1 + '?' + p2
                else:
                    path = p1

                logger.debug("%s %s %s", method, path, body[:100])
                t = time.time()
                response = client.request(method, path, body, header)
                response_body = response.read()
                t = time.time() - t
                PATH_TIME[org_path] += t
                PATH_CNT[org_path] += 1

                # handle redirects.
                if response.status_code // 10 == 30:
                    logger.debug("(%.2f[ms]) %s location=%s",
                            t*1000,
                            response.status_code, response['location'],
                            )
                    method = 'GET'
                    body = b''
                    header = {}
                    org_path = path = response['location']
                    continue
                else:
                    break

            if response.status_code // 10 == 20:
                SUCC += 1
                ok()
                logger.debug("(%.2f[ms]) %s %s",
                        t*1000,
                        response.status_code, response_body[:100])
            else:
                FAIL += 1
                ng()
                logger.warn("(%.2f[ms]) %s %s",
                        t*1000,
                        response.status_code, response_body)

def main():
    global NLOOP, SUCC, FAIL, PATH_TIME, PATH_CNT, STOP
    C1 = 1
    C2 = 1
    NLOOP = 1
    SUCC = 0
    FAIL = 0
    STOP = False
    PATH_TIME = defaultdict(int)
    PATH_CNT = defaultdict(int)

    conf = load_conf(sys.argv[1])

    loglevel = conf.get("log_level", 3)*10
    logger.setLevel(loglevel)

    vars_ = load_vars(conf)

    C1 = int(conf.get('max_request', 1))
    C2 = int(conf.get('max_scenario', C1))
    NLOOP = int(conf.get('loop', 1))
    TOTAL_DURATION = float(conf.get('total_duration', 0.0)) or None
    USER_AGENT = conf.get('user_agent', 'ghakai')

    timeout = float(conf.get('timeout', 10))
    host = conf['domain']
    headers = {'User-Agent': USER_AGENT}
    client = HTTPClient.from_url(host,
                                 concurrency=C1,
                                 connection_timeout=timeout,
                                 network_timeout=timeout,
                                 headers=headers,
                                 )

    group = gevent.pool.Pool(size=C2)
    now = time.time()
    for _ in xrange(C2):
        group.spawn(hakai, client, conf, vars_)
    group.join(TOTAL_DURATION)
    print("timeout...", file=sys.stderr)
    STOP = True
    group.kill()
    delta = time.time() - now

    NREQ = SUCC+FAIL
    req_per_sec = NREQ / delta
    print("request count:%d, concurrenry:%d, %f req/s" % (NREQ, C1, req_per_sec))
    print("SUCCESS", SUCC)
    print("FAILED", FAIL)

    total_cnt = total_time = 0

    avg_time_by_path = []
    for path,cnt in PATH_CNT.iteritems():
        t = PATH_TIME[path]
        avg_time_by_path.append((t/cnt, path))
        total_cnt += cnt
        total_time += t

    print("Average response time[ms]:", 1000*total_time/total_cnt)
    if conf.get('show_report'):
        ranking = int(conf.get('ranking', 20))
        print("Average response time for each path (order by longest) [ms]:")
        avg_time_by_path.sort(reverse=True)
        for t,p in avg_time_by_path[:ranking]:
            print(t*1000, p)


def test_indicator():
    for _ in xrange(20):
        ok(); time.sleep(0.1)
    ng(); time.sleep(0.1)
    for _ in xrange(20):
        ok(); time.sleep(0.1)
    ng(); time.sleep(0.1)
    for _ in xrange(20):
        ok(); time.sleep(0.1)
    ng(); time.sleep(0.1)

if __name__ == '__main__':
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s")
    main()
