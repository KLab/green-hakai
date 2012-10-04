#!/usr/bin/env python
# coding: utf-8
u"""インターネット破壊の gevent 版.

Ruby の internethakai より機能は少ないですが、 Ruby と gem のセットアップ
がすぐにできないときはこっちのほうが楽.
"""
from __future__ import print_function, division

import gevent.pool
from geventhttpclient import HTTPClient, URL

from collections import defaultdict
import logging
import os
import re
import sys
import time
import urllib
import urlparse
import random

logger = logging.getLogger()


class Indicator(object):

    def __init__(self, skip=10):
        self.skip = skip
        self.c = 0

    def ok(self):
        self.c += 1
        if self.c >= self.skip:
            self.c = 0
            sys.stderr.write('.')

    def ng(self):
        sys.stderr.write('x')

_indicator = Indicator()
ok = _indicator.ok
ng = _indicator.ng

basedir = '.'


def load_conf(filename):
    global basedir
    basedir = os.path.dirname(filename)
    import yaml
    return yaml.load(open(filename))

def _load_vars(conf, name):
    if name not in conf:
        return {}
    V = {}
    for var in conf[name]:
        var_name = var['name']
        var_file = var['file']
        with open(os.path.join(basedir, var_file)) as f:
            V[var_name] = f.read().splitlines()
    return V

def load_vars(conf):
    u"""設定ファイルから3種類の変数を取得する.

    consts は、 Yaml に定義した name: value をそのまま使う.
    すべてのシナリオ実行で固定した値を用いる.

    vars は、 name の値として file 内の1行の文字列をランダムに選ぶ.
    1回のシナリオ実行中は固定

    exvars は、 vars と似ているが、並列して実行しているシナリオで
    重複しないように、値をラウンドロビンで選択する.

        consts:
            aaa: AAA
            bbb: BBB
        vars:
            -
                name: foo
                file: foo.txt
        exvars:
            -
                name: bar
                file: bar.txt
    """ 
    if 'consts' in conf:
        c = conf['consts']
    else:
        c = {}
    v = _load_vars(conf, 'vars')
    e = _load_vars(conf, 'exvars')
    return (c, v, e)


class VarEnv(object):
    u"""consts, vars, exvars から、1シナリオ用の変数セットを選択する
    コンテキストマネージャー.
    コンテキスト終了時に exvars を返却する.
    """
    def __init__(self, VARS):
        self.consts = VARS[0]
        self.all_vars = VARS[1]
        self.all_exvars = VARS[2]

    def _select_vars(self):
        d = self.consts.copy()
        for k, v in self.all_vars.items():
            d[k] = random.choice(v)

        popped = {}
        for k, v in self.all_exvars.items():
            d[k] = popped[k] = v.get()
        self._popped = popped

        return d

    def __enter__(self):
        return self._select_vars()

    def __exit__(self, *err):
        for k, v in self._popped.items():
            self.all_exvars[k].put(v)


sub_name = re.compile('%\((.+?)\)%').sub

def replace_names(s, v):
    return sub_name(lambda m: v[m.group(1)], s)

def run_actions(client, conf, vars_, actions):
    global SUCC, FAIL
    org_header = conf.get('headers', {})

    # 全リクエストに付与するクエリー文字列
    query_param = [(k, replace_names(v, vars_)) for k, v in
                        conf.get('query_param', {}).items()]

    for action in actions:
        if STOP: return
        method = action.get('method', 'GET')
        org_path = path = action['path']
        header = org_header.copy()

        path = replace_names(path, vars_)

        if method == 'POST' and 'post_param' in action:
            post_param = action['post_param']
            for k, v in post_param.items():
                post_param[k] = replace_names(v, vars_)
            body = urllib.urlencode(post_param)
            header['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            body = b''

        while 1: # リダイレクトループ
            if query_param:
                if '?' in path:
                    p1, p2 = path.split('?')
                    p2 = urlparse.parse_qsl(p2) + query_param
                else:
                    p1 = path
                    p2 = query_param
                p2 = urllib.urlencode(p2)
                path = p1 + '?' + p2

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
                header = org_header.copy()
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


def hakai(client, conf, VARS):
    actions = conf['actions']
    envmgr = VarEnv(VARS)

    for _ in xrange(NLOOP):
        if STOP:
            break
        with envmgr as vars_:
            run_actions(client, conf, vars_, actions)

def make_exvars(ex):
    d = {}
    for k, v in ex.items():
        d[k] = gevent.queue.Queue(len(v), v)
    return d

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

    loglevel = conf.get("log_level", 3) * 10
    logger.setLevel(loglevel)

    C1 = int(conf.get('max_request', 1))
    C2 = int(conf.get('max_scenario', C1))
    NLOOP = int(conf.get('loop', 1))
    TOTAL_DURATION = float(conf.get('total_duration', 0.0)) or None
    USER_AGENT = conf.get('user_agent', 'ghakai')

    timeout = float(conf.get('timeout', 10))
    host = conf['domain']
    headers = {'User-Agent': USER_AGENT}

    c,v,e = load_vars(conf)
    vars_ = (c, v, make_exvars(e))

    client = HTTPClient.from_url(host,
                                 concurrency=C1,
                                 connection_timeout=timeout,
                                 network_timeout=timeout,
                                 headers=headers,
                                 )

    group = gevent.pool.Group()
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


if __name__ == '__main__':
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s")
    main()
