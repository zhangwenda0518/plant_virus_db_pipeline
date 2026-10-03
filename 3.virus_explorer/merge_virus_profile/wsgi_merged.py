"""wsgi_merged.py — explorer(/explorer/) + virus_profile(/virus/) 单进程合并入口。

用法（virus-explorer.service）：
  gunicorn --preload -w 1 --threads 2 -b 127.0.0.1:8050 wsgi_merged:server ...

原理：两个 Dash 实例挂同一个 Flask（shared_server.SERVER），URL 结构与原
两进程部署完全一致（/explorer/* 与 /virus/*，含 /virus/files/ 下载路由）。
vp 内部按 sys.modules 复用 explorer_app，df_global 等大数据只加载一份——
对比原 8050+5006 两进程部署省约 600MB 内存。

回退：ExecStart 指回 app:server，重新启用 virus-profile.service，
nginx /virus/ 指回 127.0.0.1:5006。
"""
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

os.environ["PVDB_MERGED"] = "1"
# DASH_URL_PREFIX 在下面按 app 分别设置（两个 app.py 共用这个变量名）

import shared_server  # noqa: E402

# 1) explorer 先加载，注册 sys.modules['explorer_app'] 供 vp 复用
#    注意 DASH_URL_PREFIX 是两个 app.py 共用的变量名，必须在各自 exec 前
#    设成各自的段前缀，否则 vp 会拿到 /explorer/ 导致路由冲突。
os.environ["DASH_URL_PREFIX"] = "/explorer/"
_spec = importlib.util.spec_from_file_location(
    "explorer_app", os.path.join(_HERE, "app.py"))
explorer_app = importlib.util.module_from_spec(_spec)
sys.modules["explorer_app"] = explorer_app
_spec.loader.exec_module(explorer_app)

# 2) vp 后加载：其内部发现 explorer_app 已在 sys.modules，直接复用，不再二次加载数据
os.environ["DASH_URL_PREFIX"] = "/virus/"
_vp_path = os.path.join(os.path.dirname(_HERE), "8.virus_profile", "app.py")
_spec2 = importlib.util.spec_from_file_location("virus_profile_app", _vp_path)
virus_profile_app = importlib.util.module_from_spec(_spec2)
sys.modules["virus_profile_app"] = virus_profile_app
_spec2.loader.exec_module(virus_profile_app)

server = shared_server.SERVER
assert server is not None, "PVDB_MERGED 未生效：shared_server.SERVER 为 None"
