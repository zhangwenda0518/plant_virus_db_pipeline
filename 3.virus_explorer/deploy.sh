#!/bin/bash
# ============================================================
# Plant Virus Explorer — 一键部署脚本 (阿里云 + 宝塔面板)
# ============================================================
# 用法:
#   1. 将整个 virus_explorer/ 目录上传到 /opt/virus_explorer/
#   2. 将数据文件上传到 /opt/virus_explorer/../docs/data/
#   3. bash deploy.sh
# ============================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Plant Virus Explorer 生产部署${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# ── 1. 检查 Python 环境 ──────────────────────────────
echo -e "${YELLOW}[1/6] 检查 Python 环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3，请先安装 Python 3.10+${NC}"
    exit 1
fi
PYTHON=$(python3 --version 2>&1)
echo -e "  ${GREEN}✓${NC} $PYTHON"

# 确保 config.py 在 virus_explorer 目录下
if [ ! -f /opt/virus_explorer/config.py ]; then
    echo -e "  ${YELLOW}⚠${NC} config.py 不在当前目录，请将项目根目录的 config.py 复制到 /opt/virus_explorer/"
fi

pip3 install --quiet --upgrade pip 2>/dev/null || true

# ── 2. 安装依赖 ─────────────────────────────────────
echo -e "${YELLOW}[2/6] 安装 Python 依赖...${NC}"
cd /opt/virus_explorer

# 检查数据文件
DATA_DIR=/opt/virus_explorer/data
mkdir -p "$DATA_DIR"
if [ ! -f "$DATA_DIR/Plant_Virus_Full.Info.tsv" ]; then
    echo -e "  ${YELLOW}⚠${NC} 数据文件未找到: $DATA_DIR/Plant_Virus_Full.Info.tsv"
    echo -e "  ${YELLOW}⚠${NC} 请从本地 scp 上传数据文件到 $DATA_DIR/"
    echo ""
    echo "  本地执行:"
    echo "    scp docs/data/Plant_Virus_Full.Info.tsv root@39.106.101.94:$DATA_DIR/"
    echo "    scp docs/data/Plant_Virus_Full.fasta root@39.106.101.94:$DATA_DIR/"
    echo ""
    read -p "  数据文件已上传？按 Enter 继续，Ctrl+C 取消..."
fi

pip3 install -r requirements.txt --quiet
pip3 install gunicorn --quiet
echo -e "  ${GREEN}✓${NC} 依赖安装完成"

# ── 3. 创建日志目录 ──────────────────────────────────
echo -e "${YELLOW}[3/6] 创建日志目录...${NC}"
mkdir -p /opt/virus_explorer/logs
echo -e "  ${GREEN}✓${NC} logs/ 已创建"

# ── 4. 注册 systemd 服务 ────────────────────────────
echo -e "${YELLOW}[4/6] 注册 systemd 服务...${NC}"
cp /opt/virus_explorer/plant-virus-explorer.service /etc/systemd/system/
systemctl daemon-reload
echo -e "  ${GREEN}✓${NC} 服务已注册"

# ── 5. 配置 nginx (宝塔面板路径) ────────────────────
echo -e "${YELLOW}[5/6] 配置 nginx 反向代理...${NC}"
NGINX_CONF="/www/server/panel/vhost/nginx/plant_virus_explorer.conf"
cp /opt/virus_explorer/nginx.conf "$NGINX_CONF"
# 宝塔面板 nginx 重载
if command -v nginx &> /dev/null; then
    nginx -t && nginx -s reload
    echo -e "  ${GREEN}✓${NC} nginx 配置已生效"
else
    echo -e "  ${YELLOW}⚠${NC} 未找到 nginx，请通过宝塔面板手动配置"
fi

# ── 6. 启动服务 ─────────────────────────────────────
echo -e "${YELLOW}[6/6] 启动服务...${NC}"
systemctl enable plant-virus-explorer
systemctl restart plant-virus-explorer
sleep 3
if systemctl is-active --quiet plant-virus-explorer; then
    echo -e "  ${GREEN}✓${NC} 服务运行中"
else
    echo -e "  ${RED}✗${NC} 服务启动失败，查看日志: journalctl -u plant-virus-explorer -n 50"
fi

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  访问地址:  http://39.106.101.94"
echo "  服务状态:  systemctl status plant-virus-explorer"
echo "  查看日志:  journalctl -u plant-virus-explorer -f"
echo "  重启服务:  systemctl restart plant-virus-explorer"
echo ""
echo "  确保阿里云安全组和宝塔防火墙已放行端口 80"
echo ""
