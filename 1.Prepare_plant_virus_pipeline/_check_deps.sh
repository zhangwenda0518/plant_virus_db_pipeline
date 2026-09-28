#!/bin/bash
# PlantVirusDB 依赖检查 - 在服务器上运行
set -e

echo "============================================"
echo "PlantVirusDB U1 增量更新引擎 — 依赖检查"
echo "============================================"
echo "Host: $(hostname)"
echo "Date: $(date)"
echo

# 1. Python
echo "=== 1. Python ==="
python3 --version
which python3
echo

# 2. pip packages
echo "=== 2. Python 依赖 ==="
python3 -c "
import polars; print('polars:', polars.__version__)
import Bio; print('biopython:', Bio.__version__)
import requests; print('requests:', requests.__version__)
import lxml; print('lxml:', lxml.__version__)
" 2>&1 || echo "⚠ 部分包缺失"
echo

# 3. taxonkit
echo "=== 3. taxonkit ==="
if command -v taxonkit &>/dev/null; then
    taxonkit version
else
    echo "❌ taxonkit 未安装"
    echo "   安装: wget https://github.com/shenwei356/taxonkit/releases/download/v0.15.0/taxonkit_linux_amd64.tar.gz"
    echo "         tar -xzf taxonkit_linux_amd64.tar.gz && mv taxonkit /usr/local/bin/"
fi
echo

# 4. seqkit
echo "=== 4. seqkit ==="
if command -v seqkit &>/dev/null; then
    seqkit version
else
    echo "❌ seqkit 未安装 (非必需, 全量管线 D1/F4 需要)"
fi
echo

# 5. NCBI Taxonomy data
echo "=== 5. NCBI Taxonomy 数据 ==="
TAXDIR=~/database/taxonomy
if [ -f "$TAXDIR/names.dmp" ] && [ -f "$TAXDIR/nodes.dmp" ]; then
    echo "✅ names.dmp + nodes.dmp 存在"
    ls -lh $TAXDIR/names.dmp $TAXDIR/nodes.dmp
    echo "   taxonkit 数据目录: $TAXDIR"
else
    echo "❌ Taxonomy 数据缺失"
    echo "   下载: mkdir -p $TAXDIR"
    echo "         cd $TAXDIR"
    echo "         wget https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz"
    echo "         tar -xzf taxdump.tar.gz"
fi
echo

# 6. NCBI E-utilities
echo "=== 6. NCBI 连通性 ==="
python3 -c "
from urllib.request import urlopen
import time
t0=time.time()
r=urlopen('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nucleotide&term=viruses%5Bfilter%5D&retmax=1&tool=PVDB&email=t@t.com', timeout=15)
print('NCBI OK: %d (%0.1fs)' % (r.status, time.time()-t0))
" 2>&1 || echo "❌ NCBI 不可达"
echo

# 7. API key test  (密钥只从环境变量读取, 不再硬编码; 未设置则跳过)
echo "=== 7. API Key 验证 ==="
API_KEY="${PVDB_NCBI_API_KEY:-${NCBI_API_KEY:-}}"
if [ -z "$API_KEY" ]; then
    echo "⚠ 未设置 PVDB_NCBI_API_KEY / NCBI_API_KEY, 跳过 (密钥不入库; export PVDB_NCBI_API_KEY=xxx 后重试)"
else
    PVDB_KEY="$API_KEY" python3 -c "
import os
from urllib.request import urlopen
key = os.environ['PVDB_KEY']            # 经环境变量传入, 不出现在命令行参数与日志里
r = urlopen('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=nucleotide'
            '&term=viruses%5Bfilter%5D&retmax=1&api_key=' + key + '&tool=PVDB&email=t@t.com',
            timeout=15)
import xml.etree.ElementTree as ET
xml = ET.fromstring(r.read().decode())
print('API Key OK, count=%s' % xml.find('.//Count').text)
" 2>&1 | tail -1 || echo "⚠ API Key 可能无效"
fi
echo

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# 8. Project directory
echo "=== 8. 项目目录 ==="
if [ -d "$REPO_ROOT" ]; then
    echo "✅ 项目目录存在: $REPO_ROOT"
    ls "$REPO_ROOT/1.Prepare_plant_virus_pipeline/U1_incremental_update.py" 2>/dev/null && echo "   U1 脚本已部署" || echo "   ⚠ U1 脚本未部署"
    python3 -c "import sys; sys.path.insert(0, '$REPO_ROOT'); from config import DATA_DIR; print('   DATA_DIR:', DATA_DIR)" 2>&1
else
    echo "❌ 项目目录不存在"
fi
echo

# 9. Disk
echo "=== 9. 磁盘 ==="
df -h / | tail -1
echo

echo "============================================"
echo "检查完成"
echo "============================================"
