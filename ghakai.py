#!/usr/bin/env python
# coding: utf-8
u"""インターネット破壊の gevent 版.

Ruby の internethakai より機能は少ないですが、 Ruby と gem のセットアップ
がすぐにできないときはこっちのほうが楽.
"""
from __future__ import print_function, division

__version__ = '0.0.1'

import gevent.pool
from geventhttpclient import HTTPClient

from collections import defaultdict
import logging
from optparse import OptionParser
import os
import cPickle
import re
import sys
import time
import urllib
import urlparse
import random

logger = logging.getLogger()


# 実行中に ... って表示する.
class Indicator(object):

    def __init__(self, skip=100):
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
del _indicator


def load_conf(filename):
    basedir = os.path.dirname(filename)
    import yaml
    conf = yaml.load(open(filename))
    conf.setdefault('BASEDIR', basedir)
    return conf

def _load_vars(conf, name):
    if name not in conf:
        return {}
    V = {}
    basedir = conf['BASEDIR']
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
    def __init__(self, consts, vars_, ex):
        self.consts = consts
        self.all_vars = vars_
        self.all_exvars = ex

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
    debug = logger.debug
    warn = logger.warn

    # 全リクエストに付与するクエリー文字列
    query_params = [(k, replace_names(v, vars_)) for k, v in
                        conf.get('query_params', {}).items()]

    for action in actions:
        if STOP: break
        method = action.get('method', 'GET')
        org_path = path = action['path']
        header = org_header.copy()

        path = replace_names(path, vars_)

        if method == 'POST' and 'post_params' in action:
            post_params = action['post_params']
            for k, v in post_params.items():
                post_params[k] = replace_names(v, vars_)
            body = urllib.urlencode(post_params)
            header['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            body = b''

        while 1: # リダイレクトループ
            if query_params:
                if '?' in path:
                    p1, p2 = path.split('?')
                    p2 = urlparse.parse_qsl(p2) + query_params
                else:
                    p1 = path
                    p2 = query_params
                p2 = urllib.urlencode(p2)
                path = p1 + '?' + p2

            debug("%s %s %s", method, path, body[:20])
            t = time.time()
            try:
                response = client.request(method, path, body, header)
                response_body = response.read()
                timeout = False
            except gevent.timeout as t:
                timeout = True
                break
            t = time.time() - t
            PATH_TIME[org_path] += t
            PATH_CNT[org_path] += 1

            # handle redirects.
            if response.status_code // 10 == 30:
                debug("(%.2f[ms]) %s location=%s",
                      t*1000, response.status_code, response['location'])
                method = 'GET'
                body = b''
                header = org_header.copy()
                frag = urlparse.urlparse(response['location'])
                if frag.query:
                    org_path = path = '%s?%s' % (frag.path, frag.query)
                else:
                    org_path = path = frag.path
                continue
            else:
                break

        if not timeout and response.status_code // 10 == 20:
            SUCC += 1
            ok()
            debug("(%.2f[ms]) %s %s",
                  t*1000, response.status_code, response_body[:100])
        else:
            FAIL += 1
            ng()
            if timeout:
                warn("timeout: url=%s", path)
            else:
                warn("(%.2f[ms]) %s %s",
                     t*1000, response.status_code, response_body)


def hakai(client, nloop, conf, VARS):
    actions = conf['actions']
    VARS = VarEnv(*VARS)

    for _ in xrange(nloop):
        if STOP:
            break
        with VARS as vars_:
            run_actions(client, conf, vars_, actions)

def make_exvars(ex):
    d = {}
    for k, v in ex.items():
        d[k] = gevent.queue.Queue(None, v)
    return d

def make_parser():
    parser = OptionParser(usage="%prog [options] config.yml")
    parser.add_option('--fork', type='int')
    parser.add_option('-c', '--max-request', type='int')
    parser.add_option('-n', '--loop', type='int')
    parser.add_option('-d', '--total-duration', type='float')
    parser.add_option('--max-scenario', type='int')
    parser.add_option('-v', '--verbose', action="count", default=0)
    parser.add_option('-q', '--quiet', action="count", default=0)
    return parser


def fork_call(func, args, callback):
    u"""子プロセスで func(args) を実行して、その結果を引数として callback
    を呼び出す."""
    read_end, write_end = os.pipe()
    pid = os.fork()
    if pid:
        # parent process.
        os.close(write_end)
        f = os.fdopen(read_end, 'rb')
        result = cPickle.load(f)
        if isinstance(result, BaseException):
            print(result)
            os._exit(1)
        callback(result)
        os.waitpid(pid, 0)
    else:
        # child process
        os.close(read_end)
        try:
            result = func(*args)
        except BaseException as e:
            result = e
        f = os.fdopen(write_end, 'wb')
        cPickle.dump(result, f, cPickle.HIGHEST_PROTOCOL)
        f.close()
        os._exit(0)


def main():
    global SUCC, FAIL, PATH_TIME, PATH_CNT, STOP
    SUCC = 0
    FAIL = 0
    STOP = False
    PATH_TIME = defaultdict(int)
    PATH_CNT = defaultdict(int)

    parser = make_parser()
    opts, args = parser.parse_args()
    if not args:
        parser.print_help()
        return

    conf = load_conf(args[0])

    loglevel = conf.get("log_level", 3)
    loglevel += opts.quiet - opts.verbose
    loglevel = max(loglevel, 1)
    logger.setLevel(loglevel * 10)

    max_request = opts.max_request or conf.get('max_request', 1)
    max_scenario = opts.max_scenario or conf.get('max_scenario', max_request)
    nfork = opts.fork or conf.get('fork', 1)
    nloop = opts.loop or conf.get('loop', 1)
    duration = opts.total_duration or conf.get('total_duration', None)
    user_agent = conf.get('user_agent', 'green hakai/0.1')

    timeout = float(conf.get('timeout', 10))
    host = conf['domain']

    def run_hakai(var):
        client = HTTPClient.from_url(host,
                                     concurrency=max_request,
                                     connection_timeout=timeout,
                                     network_timeout=timeout,
                                     headers={'User-Agent': user_agent},
                                     )

        group = gevent.pool.Group()
        for _ in xrange(max_scenario):
            group.spawn(hakai, client, nloop, conf, var)
        group.join(duration)
        STOP = True
        group.kill()
        return SUCC, FAIL, PATH_TIME, PATH_CNT

    consts, vars_, exvars = load_vars(conf)

    if nfork > 1:
        from threading import Thread

        results = []
        threads = []

        for ifork in xrange(nfork):
            ie = {}
            for k, v in exvars.items():
                ie[k] = v[ifork::nfork]
            var = (consts, vars_, make_exvars(ie))
            t = Thread(target=fork_call, args=(run_hakai, (var,), results.append))
            threads.append(t)

        now = time.time()
        for t in threads: t.start()
        for t in threads: t.join()
        delta = time.time() - now

        for succ, fail, path_time, path_cnt in results:
            SUCC += succ
            FAIL += fail
            for k, v in path_time.items():
                PATH_TIME[k] += v
            for k, v in path_cnt.items():
                PATH_CNT[k] += v
    else:
        var = (consts, vars_, make_exvars(exvars))
        now = time.time()
        SUCC, FAIL, PATH_TIME, PATH_CNT = run_hakai(var)
        delta = time.time() - now

    print()
    NREQ = SUCC+FAIL
    req_per_sec = NREQ / delta
    print("request count:%d, concurrenry:%d, %f req/s" % (NREQ, max_request, req_per_sec))
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
