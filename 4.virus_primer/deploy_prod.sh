#!/usr/bin/env bash
# 部署引物 Web 服务到生产 (39.106.101.94, primer-web.service, gunicorn :5000)
# 用法: bash deploy_prod.sh            # 编译检查 → 上传 → 转换 → 备份 → 落位 → 重启
#       RESTART=0 bash deploy_prod.sh  # 只落位不重启
#
# 仓库与线上的唯一差异（本脚本自动转换，不要手工改线上文件）:
#   1. Bootstrap CDN → 自托管 /lib/（jsdelivr 在境内不稳定）
#   2. BASE_TEMPLATE <style> 头部加两条导航栏 CSS（不换行防溢出）
#   线上 wsgi.py: `from step5_web_server import create_app`，跑的就是本目录同名文件。
set -euo pipefail
SRV=${SRV:-root@39.106.101.94}
REMOTE_DIR=/opt/plant_virus_db/primer_design_server
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HERE/step5_web_server.py"

echo "[1/4] 本地编译检查"
python -m py_compile "$SRC"

echo "[2/4] 上传并转换"
scp -q "$SRC" "$SRV:/tmp/step5_new.py"

echo "[3/4] 服务器端转换 + 备份 + 落位"
ssh "$SRV" REMOTE_DIR="$REMOTE_DIR" python3 - <<'PY'
import os, py_compile, shutil, tempfile, time
from pathlib import Path
remote_dir = os.environ['REMOTE_DIR']
p = Path('/tmp/step5_new.py')
t = p.read_text(encoding='utf-8')
subs = [
    ('https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css', '/lib/bootstrap.min.css'),
    ('https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css', '/lib/bootstrap-icons.css'),
    ('https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js', '/lib/bootstrap.bundle.min.js'),
]
for a, b in subs:
    assert a in t, 'repo file missing CDN link: ' + a
    t = t.replace(a, b)
anchor = 'bootstrap-icons.css" rel="stylesheet">\n    <style>\n'
assert anchor in t, 'style anchor missing'
t = t.replace(anchor,
              'bootstrap-icons.css" rel="stylesheet">\n    <style>\n'
              '        .navbar-nav .nav-link { white-space: nowrap; }\n'
              '        .navbar { flex-wrap: nowrap; }\n', 1)
tf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8')
tf.write(t)
tf.close()
py_compile.compile(tf.name, doraise=True)
live = Path(remote_dir) / 'step5_web_server.py'
if live.exists():
    bak = str(live) + '.bak_fix_' + time.strftime('%Y%m%d_%H%M%S')
    shutil.copy2(live, bak)
    print('backup ->', bak)
live.write_text(t, encoding='utf-8')
print('installed ->', live)
PY

echo "[4/4] 重启服务"
if [ "${RESTART:-1}" = "1" ]; then
    ssh "$SRV" "systemctl restart primer-web && sleep 2 && systemctl is-active primer-web"
    echo "primer-web restarted"
else
    echo "RESTART=0, 跳过重启（下次重启后生效）"
fi
