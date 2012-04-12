#!/usr/bin/env python
# coding: utf-8
from gevent.wsgi import WSGIServer

def app(env, start_response):
    start_response("200 OK", [])
    return ["Hello World"]

server = WSGIServer(('', 8889), app)
server.serve_forever()
