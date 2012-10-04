インターネット破壊(gevent)
=============================

gevent と geventhttpclient を使ったインターネット破壊の軽量版です。

インターネット破壊に比べてソースが読みやすいので、前回のリクエストの
レスポンスを使って次のリクエストを投げるようなシナリオを作るなどの
カスタマイズが簡単です。


インストール
---------------

ghakai.py を動かすために必要なライブラリを、 virtualenv をつかって構築する例です。
``$HOME/ghakai`` に virtualenv を作成し、 ``$HOME/ghakai/bin/python`` を使って
``ghakai.py`` を実行可能にしています.

::

    $ python virtualenv.py $HOME/ghakai
    $ source $HOME/ghakai/bin/activate
    (ghakai)$ pip install -r requirements.txt

ghakai.py の shebang を、 ``#!$HOME/ghakai/bin/python`` に書き換えてください。
(もちろん、 ``$HOME`` の部分は各自のホームディレクトリに書き換えてくださいね)


設定ファイル
-------------

Yaml 形式を利用しています。インターネット破壊から一部の仕様を変えています.


