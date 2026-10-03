#!/usr/bin/env python3
"""
Deploy 1KP Virome Dashboard to Alibaba Cloud production server (39.106.101.94)

2026-09-13: 源路径从 3.virus_explorer/ 迁移到 13.onekp_virus/。
已核实线上 onekp-dashboard.service 从 /opt/.../13.onekp_virus/ 运行，
onekp_app.py 与本地 13.onekp_virus/ 副本 md5 一致。
"""
import paramiko
import os
import sys
import time

HOST = "39.106.101.94"
USER = "root"
PASS = os.environ.get("ECS_ROOT_PWD", "")  # 明文口令已移除 (2026-10-03)，历史口令已泄露须轮换
PORT = 22

BASE_LOCAL = r"D:\桌面\C-host_classify\plant_virus_db_pipeline"
PROJ = "/opt/plant_virus_db/plant_virus_db_pipeline"
APP_DIR = f"{PROJ}/13.onekp_virus"

FILES_TO_UPLOAD = [
    # (local_path, remote_path)
    (f"{BASE_LOCAL}/13.onekp_virus/onekp_app.py", f"{APP_DIR}/onekp_app.py"),
    (f"{BASE_LOCAL}/13.onekp_virus/prep_onekp_data.py", f"{APP_DIR}/prep_onekp_data.py"),
    # 本地文件名带 -prod，服务器现役单元名为 onekp-dashboard.service
    (f"{BASE_LOCAL}/13.onekp_virus/onekp-dashboard-prod.service", f"{APP_DIR}/onekp-dashboard.service"),
    (f"{BASE_LOCAL}/13.onekp_virus/.cache/onekp_data.pkl", f"{APP_DIR}/.cache/onekp_data.pkl"),
    (f"{BASE_LOCAL}/13.onekp_virus/.cache/onekp_enriched.pkl", f"{APP_DIR}/.cache/onekp_enriched.pkl"),
    (f"{BASE_LOCAL}/13.onekp_virus/.cache/onekp_summary.json", f"{APP_DIR}/.cache/onekp_summary.json"),
    (f"{BASE_LOCAL}/docs/index.html", f"{PROJ}/docs/index.html"),
    (f"{BASE_LOCAL}/docs/reference_index.html", f"{PROJ}/docs/reference_index.html"),
    # 线上 nginx 是系统 nginx (/usr/sbin/nginx)，加载的是 /etc/nginx/conf.d/ 下的配置；
    # 服务器上没有宝塔 nginx (/www/server/nginx 不存在)，旧的面板路径是死路径。
    # 本地副本 2026-09-13 已从线上同步 (md5 e0c7d5fe)；若线上 conf 又改过，先拉回本地再部署。
    (f"{BASE_LOCAL}/plant-virus.conf", "/etc/nginx/conf.d/plant-virus.conf"),
]

# Result TSVs — 与应用同层 (onekp_app.py: RESULTS_DIR = BASE_DIR)
for f in ["all_viruses.best.summary.tsv", "high_conf.summary.tsv",
          "high_conf.summary.discarded.tsv"]:
    FILES_TO_UPLOAD.append(
        (f"{BASE_LOCAL}/13.onekp_virus/{f}", f"{APP_DIR}/{f}")
    )

def run_cmd(client, cmd, desc=""):
    if desc:
        print(f"  [{desc}]")
    print(f"  $ {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    if out:
        print(out[:2000])
    if err and exit_code != 0:
        print(f"  STDERR: {err[:500]}")
    return exit_code, out

def main():
    print(f"Connecting to {USER}@{HOST}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
    print("Connected.\n")

    # 1. Ensure directories exist
    print("=" * 50)
    print("[1/5] Creating directories...")
    run_cmd(client, f"mkdir -p {APP_DIR}/.cache")
    run_cmd(client, f"chown -R www:www {APP_DIR}/.cache 2>/dev/null; chmod -R 755 {APP_DIR}/.cache 2>/dev/null; echo OK")

    # 2. Upload files
    print("\n" + "=" * 50)
    print("[2/5] Uploading files...")
    sftp = client.open_sftp()
    for local, remote in FILES_TO_UPLOAD:
        if not os.path.exists(local):
            print(f"  SKIP (not found): {local}")
            continue
        fname = os.path.basename(local)
        print(f"  Upload: {fname} ({os.path.getsize(local)} bytes)")
        sftp.put(local, remote)
    sftp.close()
    print("  All files uploaded.")

    # 3. Rebuild cache on server
    print("\n" + "=" * 50)
    print("[3/5] Building data cache...")
    code, out = run_cmd(client, f"cd {APP_DIR} && python3 prep_onekp_data.py")
    # If prep fails, the manual upload of cache should still work
    if code != 0:
        print("  prep script had issues, but pre-built cache was uploaded. Continuing.")

    # 4. Install systemd service
    print("\n" + "=" * 50)
    print("[4/5] Installing systemd service...")
    run_cmd(client, f"cp {APP_DIR}/onekp-dashboard.service /etc/systemd/system/")
    run_cmd(client, "systemctl daemon-reload")
    run_cmd(client, "systemctl enable onekp-dashboard 2>/dev/null; echo done")

    # Check if pixi exists for the ExecStart path
    code, out = run_cmd(client, "which pixi 2>/dev/null || echo NO_PIXI")
    if "NO_PIXI" in out:
        print("  pixi not found, adjusting service to use python3 directly...")
        # Update the service file to use python3
        run_cmd(client, f"sed -i 's|ExecStart=.*|ExecStart=/usr/bin/python3.8 {APP_DIR}/onekp_app.py|' /etc/systemd/system/onekp-dashboard.service")
        run_cmd(client, "systemctl daemon-reload")

    # 5. Start service
    print("\n" + "=" * 50)
    print("[5/5] Starting service...")
    run_cmd(client, "systemctl stop onekp-dashboard 2>/dev/null; echo stopped")
    time.sleep(2)
    run_cmd(client, "systemctl start onekp-dashboard")
    time.sleep(4)
    code, out = run_cmd(client, "systemctl status onekp-dashboard --no-pager -l")

    # Test
    code, out = run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8051/onekp/ 2>/dev/null || echo 'NOT_RUNNING'")
    if "200" in out:
        print("\n  *** Service responding with HTTP 200! ***")
    else:
        print(f"\n  Service response: {out[:100]}")
        print("  Checking logs...")
        run_cmd(client, "journalctl -u onekp-dashboard --no-pager -n 20")

    # 6. Reload nginx
    print("\n" + "=" * 50)
    print("[6/6] Testing & reloading nginx...")
    run_cmd(client, "nginx -t")
    run_cmd(client, "systemctl reload nginx")
    print("  Nginx reloaded.")

    client.close()
    print("\n" + "=" * 50)
    print("DEPLOY COMPLETE!")
    print(f"Access: http://{HOST}/onekp/")
    print("=" * 50)

if __name__ == "__main__":
    main()
