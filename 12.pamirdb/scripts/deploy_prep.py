"""
PAmiRDB Deployment Preparer for http://39.106.101.94/pamirdb/

Usage:
  python deploy_prep.py

Creates deploy/ directory with:
  - backend/server.py (patched for sub-path)
  - backend/index.html (patched API path)
  - scripts/ (all modules)
  - data/ (predictions)
  - nginx_pamirdb.conf
  - deploy.sh
"""
import shutil, json
from pathlib import Path

SRC = Path(__file__).parent.parent  # pamirdb/ root
DEPLOY = SRC / "deploy"
API_PATH = "/pamirdb/api"

# Clean
if DEPLOY.exists():
    shutil.rmtree(DEPLOY)

# Copy scripts
(DEPLOY / "scripts").mkdir(parents=True)
for f in SRC.glob("scripts/*.py"):
    if f.is_file():
        shutil.copy2(f, DEPLOY / "scripts" / f.name)

# Copy backend files (not dirs)
(DEPLOY / "backend").mkdir()
for f in SRC.glob("backend/*"):
    if f.is_file():
        shutil.copy2(f, DEPLOY / "backend" / f.name)

# Copy data
(DEPLOY / "data").mkdir()
for f in SRC.glob("data/predictions*.json"):
    shutil.copy2(f, DEPLOY / "data" / f.name)
for f in SRC.glob("data/plant_mirnas.*"):
    shutil.copy2(f, DEPLOY / "data" / f.name)
for f in SRC.glob("data/viruses.*"):
    shutil.copy2(f, DEPLOY / "data" / f.name)
# Copy virus_host if exists
vh = SRC / "data" / "virus_host.csv"
if vh.exists():
    shutil.copy2(vh, DEPLOY / "data" / "virus_host.csv")

# Write nginx config directly
nginx_conf = DEPLOY / "nginx_pamirdb.conf"
nginx_conf.write_text("""# Nginx config for http://39.106.101.94/pamirdb/
location /pamirdb/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 120s;
}
""")
print(f"Created: {nginx_conf.name}")

# Patch index.html - make API path detect deployment context
index = DEPLOY / "backend" / "index.html"
html = index.read_text(encoding='utf-8')

# Replace hardcoded API path with auto-detection
old_api = "const API = '/api';"
new_api = """// Auto-detect deployment path
const API = (window.location.pathname.includes('/pamirdb/') 
    ? '/pamirdb/api' : '/api');"""
html = html.replace(old_api, new_api)

index.write_text(html, encoding='utf-8')
print(f"Patched: {index.name}")

# Create deploy.sh for server-side setup
deploy_sh = DEPLOY / "deploy.sh"
deploy_sh.write_text(r"""#!/bin/bash
# PAmiRDB Deployment Script for Alibaba Cloud (阿里云)
# Run as root or with sudo

set -e
echo "=== PAmiRDB Deployment ==="

# 1. Install Python 3 (if needed)
if ! command -v python3 &> /dev/null; then
    echo "Installing Python3..."
    yum install -y python3 || apt-get install -y python3
fi

# 2. Create directory
APP_DIR=/opt/pamirdb
mkdir -p $APP_DIR
cp -r scripts/ backend/ data/ $APP_DIR/
echo "Files copied to $APP_DIR"

# 3. Create systemd service
cat > /etc/systemd/system/pamirdb.service << 'EOF'
[Unit]
Description=PAmiRDB miRNA-Virus Target Prediction Service
After=network.target

[Service]
Type=simple
User=nobody
WorkingDirectory=/opt/pamirdb
ExecStart=/usr/bin/python3 backend/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 4. Configure Nginx
if [ -f /etc/nginx/nginx.conf ]; then
    cp nginx_pamirdb.conf /etc/nginx/conf.d/pamirdb.conf
    nginx -t && systemctl reload nginx
    echo "Nginx configured"
else
    echo "WARNING: Nginx not found. Skipping Nginx config."
    echo "Install Nginx: yum install -y nginx"
fi

# 5. Start service
systemctl daemon-reload
systemctl enable pamirdb
systemctl start pamirdb
echo "PAmiRDB service started"

# 6. Open firewall
if command -v firewall-cmd &> /dev/null; then
    firewall-cmd --permanent --add-service=http
    firewall-cmd --reload
elif command -v ufw &> /dev/null; then
    ufw allow 80/tcp
fi

echo ""
echo "=== Deployment Complete ==="
echo "Access: http://39.106.101.94/pamirdb/"
echo "Check:  systemctl status pamirdb"
echo "Logs:   journalctl -u pamirdb -f"
""")
print(f"Created: {deploy_sh.name}")
# Note: chmod doesn't work on Windows; user runs chmod +x on server

print(f"\nDeploy package ready: {DEPLOY}")
print("Upload to server and run: bash deploy.sh")
