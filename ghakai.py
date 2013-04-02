#!/usr/bin/env python
# coding: utf-8
u"""インターネット破壊の gevent 版.

Ruby の internethakai より機能は少ないですが、 Ruby と gem のセットアップ
がすぐにできないときはこっちのほうが楽.

Python 2.6 以降に対応.
"""
from __future__ import print_function, division

__version__ = '0.0.1'

import gevent.pool
import geventhttpclient.client
from geventhttpclient.connectionpool import ConnectionPool

from collections import defaultdict
import logging
from optparse import OptionParser
import os
import re
import sys
import time
import urllib
import urlparse
import random
import socket


debug = logging.debug
info = logging.info
warn = logging.warn
error = logging.error

SUCC = FAIL = 0
STOP = False


class AddressConnectionPool(ConnectionPool):
    addresses = []

    @classmethod
    def register_addresslist(cls, addresslist):
        for addr in addresslist:
            port = 80
            if ':' in addr:
                addr, port = addr.split(':')
                port = int(port)
                cls.addresses += socket.getaddrinfo(
                        addr, port,
                        socket.AF_INET, socket.SOCK_STREAM, socket.SOL_TCP, 0)

    def _resolve(self):
        """returns (family, socktype, proto, cname, addr)"""
        if not self.addresses:
            self.addresses = ConnectionPool._resolve(self)
        random.shuffle(self.addresses)
        return self.addresses

geventhttpclient.client.ConnectionPool = AddressConnectionPool

MIMETYPE_FORM = 'application/x-www-form-urlencoded'
MIMETYPE_JSON = 'application/json'


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


class Action(object):
    def __init__(self, conf, action):
        self.conf = conf
        self.action = action
        self.method = action.get('method', 'GET')
        self.path = action['path']
        #: 全リクエストに付与するクエリー文字列
        self.query_params = conf.get('query_params', {}).items()
        self.headers = conf.get('headers', {})
        self.post_params = conf.get('post_params')
        self._scan_exp = None
        scan = action.get('scan')
        if scan:
            self._scan_r = re.compile(scan)
        else:
            self._scan_r = None

    def _scan(self, response_body, vs):
        u"""conf['scan'] で指定された正規表現でチェック&変数キャプチャする"""
        if not self._scan_r:
            return True
        m = self._scan_r.search(response_body)
        if not m:
            return False
        vs.update(m.groupdict(''))
        return True

    def _replace_names(self, s, v, _sub_name=re.compile('%\((.+?)\)%').sub):
        return _sub_name(lambda m: v[m.group(1)], s)

    def execute(self, client, vars_):
        u"""1アクションの実行

        リダイレクトを処理するのでリクエストは複数回実行する
        """
        method = self.method
        #: path - 変数展開前のURL
        #: この path ごとに集計を行う.
        path = self.path
        query_params = [(k, self._replace_names(v, vars_))
                        for (k, v) in self.query_params]
        header = self.headers

        #: realpath - 変数展開した実際にアクセスするURL
        real_path = self._replace_names(path, vars_)

        if method == 'POST' and self.post_params is not None:
            post_params = [(k, self._replace_names(v, vars_))
                           for (k, v) in self.post_params.items()]
            body = urllib.urlencode(post_params)
            header = header.copy()
            header['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            body = b''

        while 1:  # リダイレクトループ
            if query_params:
                if '?' in real_path:
                    p1, p2 = real_path.split('?')
                    p2 = urlparse.parse_qsl(p2) + query_params
                else:
                    p1 = real_path
                    p2 = query_params
                p2 = urllib.urlencode(p2)
                real_path = p1 + '?' + p2

            debug("%s %s %s", method, real_path, body[:20])
            t = time.time()
            try:
                timeout = False
                response = client.request(method, real_path, body, header)
                response_body = response.read()
            except (gevent.timeout, gevent.socket.timeout):
                timeout = True
                response = None
                break
            except IOError as e:
                response = None
                err = e
                break
            finally:
                # t はエラー時も使われるので常に計測する.
                t = time.time() - t

            PATH_TIME[path] += t
            PATH_CNT[path] += 1

            if response.status_code // 10 != 30:  # isn't redirect
                break

            # handle redirects.
            debug("(%.2f[ms]) %s location=%s", t*1000,
                  response.status_code, response['location'])
            method = 'GET'
            body = b''
            headers = self.headers
            frag = urlparse.urlparse(response['location'])
            if frag.query:
                path = real_path = '%s?%s' % (frag.path, frag.query)
            else:
                path = real_path = frag.path

        if timeout:
            succ = False
        elif not (response and response.status_code // 10 == 20):
            succ = False
        else:
            succ = self._scan(response_body, vars_)

        if succ:
            global SUCC
            SUCC += 1
            ok()
            debug("(%.2f[ms]) %s %s",
                  t*1000, response.status_code, response_body[:100])
            return True
        else:
            global FAIL
            FAIL += 1
            ng()
            if response:
                warn("(%.2f[ms]) %s %s",
                     t*1000, response.status_code, response_body)
            elif timeout:
                warn("\ntimeout: time=%.2f[sec] url=%s", t, path)
            else:
                error("time=%.2f[sec] url=%s error=%s", t, path, err)
            return False


def run_actions(client, conf, vars_, actions):
    succ = True
    for action in actions:
        if STOP or not succ:
            break
        succ = action.execute(client, vars_)


def hakai(client, conf, VARS):
    global LOOP
    actions = [Action(conf, a) for a in conf['actions']]
    VARS = VarEnv(*VARS)

    while True:
        if STOP:
            break
        LOOP -= 1
        if LOOP < 0:
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
    parser.add_option('-f', '--fork', type='int')
    parser.add_option('-c', '--max-request', type='int')
    parser.add_option('-n', '--loop', type='int')
    parser.add_option('-d', '--total-duration', type='float')
    parser.add_option('-s', '--max-scenario', type='int')
    parser.add_option('-v', '--verbose', action="count", default=0)
    parser.add_option('-q', '--quiet', action="count", default=0)
    return parser


def update_conf(conf, opts):
    u"""設定ファイルの内容をコマンドラインオプションで上書きする"""
    conf['max_scenario'] = int(opts.max_scenario or
                               conf.get('max_scenario', 1))
    conf['max_request'] = int(opts.max_request or
                              conf.get('max_request', conf['max_scenario']))
    conf['loop'] = int(opts.loop or conf.get('loop', 1))
    conf['total_duration'] = opts.total_duration or conf.get('total_duration')


def run_hakai(conf, all_vars):
    u"""各プロセスで動くmain関数"""
    global SUCC, FAIL, PATH_TIME, PATH_CNT, STOP, LOOP
    SUCC = 0
    FAIL = 0
    LOOP = conf['loop'] * conf['max_scenario']
    STOP = False
    PATH_TIME = defaultdict(int)
    PATH_CNT = defaultdict(int)

    addresslist = conf.get('addresslist')
    if addresslist:
        AddressConnectionPool.register_addresslist(addresslist)

    host = conf['domain']
    user_agent = conf.get('user_agent', 'green hakai/0.1')
    timeout = float(conf.get('timeout', 10))
    client = geventhttpclient.HTTPClient.from_url(
            host,
            concurrency=conf['max_request'],
            connection_timeout=timeout,
            network_timeout=timeout,
            headers={'User-Agent': user_agent},
            )

    vars_ = all_vars[0], all_vars[1], make_exvars(all_vars[2])

    group = gevent.pool.Group()
    for _ in xrange(conf['max_scenario']):
        group.spawn(hakai, client, conf, vars_)
    group.join(conf['total_duration'])
    STOP = True
    group.kill()
    return SUCC, FAIL, dict(PATH_TIME), dict(PATH_CNT)


def remote_main(channel):
    u"""run_hakai() をリモートで動かすエージェント"""
    conf, vars_ = channel.receive()
    result = run_hakai(conf, vars_)
    channel.send(result)


def build_specs(conf, opts):
    u"""conf, opts から execnet 用の spec を作る"""
    if opts.fork:
        return ['popen'] * opts.fork
    nodes = conf.get('nodes')
    if not nodes:
        return ['popen'] * conf.get('fork', 1)

    specs = []
    for node in nodes:
        host = node['host']
        if host == 'localhost':
            s = 'popen'
        else:
            # リモートの Python も同じ場所に有ることを仮定する
            s = "ssh=" + host + "//python=" + sys.executable
        specs += [s] * node['proc']

    return specs


def main():
    parser = make_parser()
    opts, args = parser.parse_args()
    if not args:
        parser.print_help()
        return

    conf = load_conf(args[0])
    update_conf(conf, opts)

    loglevel = conf.get("log_level", 3)
    loglevel += opts.quiet - opts.verbose
    loglevel = max(loglevel, 1)
    logging.getLogger().setLevel(loglevel * 10)

    specs = build_specs(conf, opts)
    procs = len(specs)

    if specs == ['popen']:
        # ローカル1プロセスの場合は直接実行する.
        now = time.time()
        SUCC, FAIL, PATH_TIME, PATH_CNT = run_hakai(conf, load_vars(conf))
        delta = time.time() - now
    else:
        import execnet
        import ghakai
        group = execnet.Group(specs)
        multi_chan = group.remote_exec(ghakai)

        all_vars = []
        consts, vars_, exvars = load_vars(conf)
        for i in xrange(procs):
            ie = {}
            for k, v in exvars.items():
                ie[k] = v[i::procs]
            all_vars.append((consts, vars_, ie))

        now = time.time()
        for v, ch in zip(all_vars, multi_chan):
            ch.send((conf, v))
        results = multi_chan.receive_each()
        delta = time.time() - now

        SUCC = 0
        FAIL = 0
        PATH_TIME = defaultdict(int)
        PATH_CNT = defaultdict(int)
        for succ, fail, path_time, path_cnt in results:
            SUCC += succ
            FAIL += fail
            for k, v in path_time.items():
                PATH_TIME[k] += v
            for k, v in path_cnt.items():
                PATH_CNT[k] += v

    print()
    NREQ = SUCC + FAIL
    req_per_sec = NREQ / delta
    print("request count:%d, concurrenry:%d, %f req/s" %
          (NREQ, conf['max_request'] * procs, req_per_sec))
    print("SUCCESS", SUCC)
    print("FAILED", FAIL)

    total_cnt = total_time = 0

    avg_time_by_path = []
    for path, cnt in PATH_CNT.iteritems():
        t = PATH_TIME[path]
        avg_time_by_path.append((t/cnt, path))
        total_cnt += cnt
        total_time += t

    print("Average response time[ms]:", 1000*total_time/total_cnt)
    if conf.get('show_report'):
        ranking = int(conf.get('ranking', 20))
        print("Average response time for each path (order by longest) [ms]:")
        avg_time_by_path.sort(reverse=True)
        for t, p in avg_time_by_path[:ranking]:
            print(t*1000, p)


if __name__ == '__main__':
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s")
    main()

elif __name__ == '__channelexec__':
    # execnet 経由で実行される場合.
    remote_main(channel)
