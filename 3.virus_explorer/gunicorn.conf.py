"""
Gunicorn 生产配置 — Plant Virus Explorer
=========================================
启动: gunicorn -c gunicorn.conf.py app:server
"""
import os, multiprocessing

# 绑定地址（仅本地，由 nginx 反向代理）
bind = "127.0.0.1:8050"

# Worker 数量 (2 核机器推荐 2-4)
workers = 2
threads = 2

# Worker 类型
worker_class = "sync"

# 超时设置（数据加载需要时间）
timeout = 120
graceful_timeout = 30

# 日志
accesslog = os.path.join(os.path.dirname(__file__), "logs", "gunicorn_access.log")
errorlog = os.path.join(os.path.dirname(__file__), "logs", "gunicorn_error.log")
loglevel = "info"

# 进程命名
proc_name = "plant_virus_explorer"

# 预加载应用（节省内存，但代码改动后需重启）
preload_app = True

# 最大请求数后重启 worker（防止内存泄漏）
max_requests = 1000
max_requests_jitter = 100
