#!/usr/bin/env python3
"""phylo_offload.py — MAFFT+FastTree 中转到 246 计算服务器的桥接层（跑在 39 上）。

拓扑：39（公网 web，2 核 3.5G）↔ 246（校园网计算节点，256 核 644G）。
39 连不进校园网，246 能出站连 39 —— 只有 pull 模式可行：

    39 应用     ：把 input.fa 丢进 spool 任务目录（本模块负责）
    246 worker  ：出站 SSH 轮询 spool，mkdir 原子抢占，scp 拉走 → 跑
                  mafft + fasttree → scp 回传 aligned.fa / rtt.nwk / done.json
    39 应用     ：本地轮询自己磁盘上的 done.json（同机检查，零成本）

两级保险，任何一环挂掉都不影响网页可用性：
  · worker 心跳：worker 每轮 touch {SPOOL}/heartbeat；worker_alive() 超过
    HEARTBEAT_STALE 秒没心跳 → 视为离线，调用方直接本地跑，不让用户干等。
  · 任务级：run_align_tree_remote 超过 REMOTE_TIMEOUT 仍无结果 → 返回 None，
    调用方回退本地执行（rtt_module.run_rtt 负责回退）。
"""
import json
import os
import shutil
import time
import uuid

# spool 就放在本模块同目录下（即 39 的 virus_explorer/）
SPOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'phylo_jobs')

HEARTBEAT_STALE = 180   # 心跳超过 3 分钟视为 worker 离线
POLL_INTERVAL = 2.0     # 本地查 done.json 的间隔（同机磁盘，便宜）
REMOTE_TIMEOUT = 600    # 等远程结果上限；超时返回 None 让调用方回退本地。
                        # 246 上 30 条序列的 mafft+fasttree 通常几十秒内完成，
                        # 600s 只兜"worker 拉起后中途死了"这种罕见情况。


def worker_alive():
    """246 worker 最近 HEARTBEAT_STALE 秒内有心跳吗？没有就别投远程了。"""
    try:
        return (time.time() - os.path.getmtime(
            os.path.join(SPOOL, 'heartbeat'))) < HEARTBEAT_STALE
    except OSError:
        return False


def run_align_tree_remote(input_fa, aln_out, tree_out):
    """提交比对+建树任务，阻塞到 246 回传完成。

    返回 {'t_mafft', 't_tree', 't_remote'}（秒）；超时 / worker 报错 /
    回传不完整 → None，调用方应回退本地。
    """
    os.makedirs(SPOOL, exist_ok=True)
    jid = time.strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:6]
    jd = os.path.join(SPOOL, jid)
    os.makedirs(jd)
    shutil.copy(input_fa, os.path.join(jd, 'input.fa'))
    with open(os.path.join(jd, 'job.json'), 'w') as f:
        json.dump({'id': jid, 'status': 'pending', 'created': time.time()}, f)

    deadline = time.time() + REMOTE_TIMEOUT
    while time.time() < deadline:
        if os.path.isfile(os.path.join(jd, 'done.json')):
            try:
                with open(os.path.join(jd, 'done.json')) as f:
                    meta = json.load(f)
            except Exception:
                meta = {}
            if meta.get('ok') \
                    and os.path.isfile(os.path.join(jd, 'aligned.fa')) \
                    and os.path.isfile(os.path.join(jd, 'rtt.nwk')):
                shutil.copy(os.path.join(jd, 'aligned.fa'), aln_out)
                shutil.copy(os.path.join(jd, 'rtt.nwk'), tree_out)
                shutil.rmtree(jd, ignore_errors=True)  # 结果已取走，清现场
                return {'t_mafft': float(meta.get('t_mafft', 0.0)),
                        't_tree': float(meta.get('t_tree', 0.0)),
                        't_remote': float(meta.get('t_total', 0.0))}
            return None  # worker 明确报错 → 立刻回退，不再傻等
        time.sleep(POLL_INTERVAL)
    return None
