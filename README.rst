インターネット破壊(gevent)
=============================

gevent と geventhttpclient を使ったインターネット破壊の軽量版です。

インターネット破壊に比べてソースが読みやすいので、前回のリクエストの
レスポンスを使って次のリクエストを投げるようなシナリオを作るなどの
カスタマイズが簡単です。


インストール
---------------

ghakai.py を動かすために必要なライブラリを、 virtualenv をつかって構築する例です。

::

    $ wget http://raw.github.com/pypa/virtualenv/master/virtualenv.py
    $ python virtualenv.py $HOME/ghakai
    $ source $HOME/ghakai/bin/activate
    (ghakai)$ pip install http://gevent.googlecode.com/files/gevent-1.0b2.tar.gz
    (ghakai)$ pip install https://github.com/gwik/geventhttpclient/tarball/master
    (ghakai)$ pip install PyYaml

ghakai.py の shebang を、 ``#!$HOME/ghakai/bin/python`` に書き換えてください。
(もちろん、 ``$HOME`` の部分は各自のホームディレクトリに書き換えてくださいね)


HTTPClientについて
-------------------

Python の標準ライブラリではなく、HTTPヘッダの解析が高速な geventhttpclient の
HTTPClient を利用しています。
get, post, put などのメソッドがあるので、それを呼んでください。

https://github.com/gwik/geventhttpclient/blob/master/src/geventhttpclient/client.py

