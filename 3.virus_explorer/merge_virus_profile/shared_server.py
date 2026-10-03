"""shared_server.py — 合并部署时 explorer 与 virus_profile 共用的 Flask 实例。

仅当环境变量 PVDB_MERGED=1（由 wsgi_merged.py 设置）时创建；否则 SERVER=None，
两个 app.py 里 Dash(server=None) 走默认行为（各自独立 Flask），原两进程部署
完全不受影响。
"""
import os

import flask

SERVER = flask.Flask("plantvirus_merged") if os.environ.get("PVDB_MERGED") == "1" else None
