#!/bin/bash
# 部署 Photo Gallery 到 39.106.101.94
# 用法: bash deploy_photos.sh

SERVER="root@39.106.101.94"
REMOTE_DIR="/opt/plant_virus_db/reference"

echo "=== 1. 同步静态文件到服务器 ==="
rsync -avz --progress \
    docs/photos.html \
    docs/data/eppo_gallery.json \
    ${SERVER}:${REMOTE_DIR}/

echo ""
echo "=== 2. 同步更新导航栏的其他页面 ==="
rsync -avz --progress \
    docs/index.html \
    docs/segmented.html \
    docs/nonsegmented.html \
    docs/download.html \
    docs/explorer.html \
    docs/submit.html \
    ${SERVER}:${REMOTE_DIR}/

echo ""
echo "=== 3. 重启 nginx (如需要) ==="
ssh ${SERVER} "nginx -t && nginx -s reload || echo 'nginx reload skipped'"

echo ""
echo "Done! 访问 http://39.106.101.94/reference/photos.html"
