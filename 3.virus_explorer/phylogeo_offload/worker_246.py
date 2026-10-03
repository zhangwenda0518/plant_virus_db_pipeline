#!/usr/bin/env python3
"""worker_246.py — 跑在 246 上，拉取 39 的 phylo_jobs 任务并回传结果。

运行方式（无需 root）：
    crontab: * * * * * flock -n /tmp/phylogeo_worker.lock \
                 python3 ~/phylogeo_worker/worker_246.py >> ~/phylogeo_worker/worker.log 2>&1

cron 每分钟拉起一次作看门狗；进程内每 POLL 秒轮询一轮、存活 RUN_SECONDS
秒后退出让位给下一次 cron。flock 保证任意时刻只有一个实例在轮询。
所有 SSH/SCP 均由 246 出站发起（39 在公网、246 在校园网内，反向不通）。
"""

import json
import os
import shlex
import shutil
import subprocess
import time

HOST = 'root@39.106.101.94'
SPOOL = '/opt/plant_virus_db/plant_virus_db_pipeline/virus_explorer/phylo_jobs'
WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work')

MAFFT = os.path.expanduser('~/.pixi/bin/mafft')            # v7.525
FASTTREE = '/home/zhangwenda/mambaforge/bin/fasttree'
THREADS = '8'                                              # mafft --thread

POLL = 3.0              # 轮询 39 spool 的间隔（ControlMaster 复用连接，开销小）
RUN_SECONDS = 55.0      # 每次被 cron 拉起后存活时长
MAFFT_TIMEOUT = 900
FASTTREE_TIMEOUT = 1800
JOB_DIR_MAX_AGE_MIN = 120   # spool 里超过 2 小时的任务目录一律清掉
CLAIM_STALE_MIN = 30        # claim 超过 30 分钟视为上次 worker 中途死了，放开重抢

SSH_BASE = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'ControlMaster=auto', '-o', 'ControlPersist=300',
            '-o', 'ControlPath=/tmp/ssh-phylo-%r@%h-%p']
SCP_BASE = ['scp', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'ControlMaster=auto', '-o', 'ControlPersist=300',
            '-o', 'ControlPath=/tmp/ssh-phylo-%r@%h-%p']


def ssh_run(remote_cmd, timeout=60):
    # 注意：cron 环境的 /usr/bin/python3 较老（无 capture_output/text 参数），
    # 全文件一律用 stdout/stderr=PIPE + universal_newlines 的兼容写法。
    return subprocess.run(SSH_BASE + [HOST, remote_cmd],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=timeout)


def scp_down(remote_path, local_path):
    return subprocess.run(SCP_BASE + ['%s:%s' % (HOST, remote_path), local_path],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=300)


def scp_up(local_path, remote_path):
    return subprocess.run(SCP_BASE + [local_path, '%s:%s' % (HOST, remote_path)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=300)


def jq(path):
    """给远程路径加引号，防路径里的意外字符。"""
    return shlex.quote(path)


def heartbeat():
    ssh_run('mkdir -p %s && touch %s' % (jq(SPOOL), jq(os.path.join(SPOOL, 'heartbeat'))))


def list_jobs():
    r = ssh_run('ls -d %s/*/job.json 2>/dev/null' % jq(SPOOL))
    out = []
    for line in r.stdout.split():
        # .../phylo_jobs/<jid>/job.json
        out.append(line.rstrip('/job.json').split('/')[-1])
    return out


def try_claim(jid):
    """原子抢占：mkdir claim 成功即抢到；已存在（别人在跑/已完成）则跳过。
    同时跳过已有 done/error 的任务。"""
    jd = os.path.join(SPOOL, jid)
    cmd = ('test ! -e {done} && test ! -e {err} && mkdir {claim} 2>/dev/null'
           ' && echo CLAIMED || echo BUSY').format(
        done=jq(os.path.join(jd, 'done.json')),
        err=jq(os.path.join(jd, 'error.json')),
        claim=jq(os.path.join(jd, 'claim')))
    return ssh_run(cmd).stdout.strip().endswith('CLAIMED')


def reap_stale_claims():
    """上次 worker 中途死掉留下的 claim（超 CLAIM_STALE_MIN 分钟）删掉，
    任务回到可抢占状态。"""
    ssh_run('find %s -maxdepth 2 -type d -name claim -mmin +%d -exec rm -rf {{}} +'
            % (jq(SPOOL), CLAIM_STALE_MIN))


def cleanup_old_jobs():
    ssh_run('find %s -maxdepth 1 -type d -name "2*" -mmin +%d -exec rm -rf {{}} +'
            % (jq(SPOOL), JOB_DIR_MAX_AGE_MIN))


def fail_job(jid, msg):
    """把错误写回 39，让等待方立刻回退本地，不要傻等超时。"""
    up = os.path.join(WORK, jid, 'error.json')
    try:
        with open(up, 'w') as f:
            json.dump({'ok': False, 'error': str(msg)[:500], 'worker': '246',
                       'finished': time.time()}, f)
        scp_up(up, os.path.join(SPOOL, jid, 'error.json'))
    except Exception as e:
        print('[worker] fail_job also failed:', e, flush=True)


def process(jid):
    """拉取 → mafft → fasttree → 回传。任何失败都写 error.json 回去。"""
    os.makedirs(WORK, exist_ok=True)
    wd = os.path.join(WORK, jid)
    os.makedirs(wd, exist_ok=True)
    t0 = time.time()
    try:
        jd = os.path.join(SPOOL, jid)
        r = scp_down(jq(os.path.join(jd, 'input.fa')), os.path.join(wd, 'input.fa'))
        if r.returncode != 0:
            raise RuntimeError('scp input.fa: %s' % r.stderr[:200])

        aln = os.path.join(wd, 'aligned.fa')
        with open(aln, 'w') as fo:
            p = subprocess.run([MAFFT, '--auto', '--quiet', '--thread', THREADS,
                                os.path.join(wd, 'input.fa')],
                               stdout=fo, stderr=subprocess.PIPE,
                               universal_newlines=True,
                               timeout=MAFFT_TIMEOUT)
            if p.returncode != 0:
                raise RuntimeError('mafft rc=%d: %s' % (p.returncode, p.stderr[:200]))
        if not os.path.getsize(aln):
            raise RuntimeError('mafft produced empty alignment')
        t_mafft = time.time() - t0

        t1 = time.time()
        tree = os.path.join(wd, 'rtt.nwk')
        with open(tree, 'w') as fo:
            p = subprocess.run([FASTTREE, '-nt', '-gtr', '-quiet', aln],
                               stdout=fo, stderr=subprocess.PIPE,
                               universal_newlines=True,
                               timeout=FASTTREE_TIMEOUT)
            if p.returncode != 0:
                raise RuntimeError('fasttree rc=%d: %s' % (p.returncode, p.stderr[:200]))
        if not os.path.getsize(tree):
            raise RuntimeError('fasttree produced empty tree')
        t_tree = time.time() - t1

        done = os.path.join(wd, 'done.json')
        with open(done, 'w') as f:
            json.dump({'ok': True, 't_mafft': round(t_mafft, 1),
                       't_tree': round(t_tree, 1),
                       't_total': round(time.time() - t0, 1),
                       'worker': '246', 'finished': time.time()}, f)
        for name in ('aligned.fa', 'rtt.nwk', 'done.json'):
            r = scp_up(os.path.join(wd, name), os.path.join(jd, name))
            if r.returncode != 0:
                raise RuntimeError('scp up %s: %s' % (name, r.stderr[:200]))
        print('[worker] job %s done: mafft %.1fs fasttree %.1fs'
              % (jid, t_mafft, t_tree), flush=True)
    except Exception as e:
        print('[worker] job %s FAILED: %s' % (jid, e), flush=True)
        fail_job(jid, e)
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def main():
    start = time.time()
    while time.time() - start < RUN_SECONDS:
        try:
            heartbeat()
            reap_stale_claims()
            cleanup_old_jobs()
            for jid in list_jobs():
                if try_claim(jid):
                    process(jid)
        except Exception as e:
            print('[worker] loop error:', e, flush=True)
        time.sleep(POLL)


if __name__ == '__main__':
    main()
