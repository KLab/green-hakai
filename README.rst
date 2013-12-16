インターネット破壊(gevent)
=============================

`gevent <http://www.gevent.org/>`_ と `geventhttpclient <https://github.com/gwik/geventhttpclient>`_
を使ったインターネット破壊の軽量版です。

インターネット破壊に比べてソースが読みやすいので、前回のリクエストの
レスポンスを使って次のリクエストを投げるようなシナリオを作るなどの
カスタマイズが簡単です。


インストール
---------------

::

    pip install https://github.com/KLab/green-hakai/archive/master.zip

`virtualenv <http://www.virtualenv.org/>`_ の利用を推奨します。
(`virtualenv のインストール手順 <http://www.virtualenv.org/en/latest/virtualenv.html#installation>`_)


設定ファイル
-------------

Yaml 形式を利用しています。インターネット破壊から一部の仕様を変えています.
利用できるオプションとその意味については、 `example/sample.yml` を参照してください。

いくつかのオプションはコマンドライン引数で変更できます。


並列実行
---------

1つのシナリオでは、 actions をひと通り実行します。

max-scenario オプションでは、1プロセス当たり、何シナリオを並列して実行するか
(シナリオ実行スレッドの数)を設定します。

loop オプションは、各シナリオ実行スレッドが何回シナリオを実行するかを指定します。

fork オプションはプロセスの数を指定します。最終的に実行されるシナリオの本数は、
max-scenario * loop * fork になります。

10000ユーザーが同時にアクセスしているけど、本当に同時に来るリクエスト数は100程度
というケースをシミュレートするために、 max-request というオプションもあります。
このオプションは、同時に実行するリクエスト数を制限します。
省略すると、 max-scenario と同じ値になります。
max-scenario より大きい値を設定しても無意味です。

コマンドラインで負荷を調整したい場合、設定ファイルでは何も設定せず、コマンドラインオプションで
``-s`` (``--max-scenario``) を使って並列シナリオ数を設定し、必要があれば ``-c`` (``--max-request``)
を設定することです。

