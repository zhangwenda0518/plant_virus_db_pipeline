#!/usr/bin/env python3
"""从 stdin 读 git diff 的 +行，检出疑似密钥/口令；命中则打印并返回退出码 1。

被 scripts/.githooks/pre-commit 调用；也可独立使用：
    git diff -U0 | python scripts/check_secrets.py
"""
import re
import sys

# 已泄露过的真实凭据字面量（吊销前的指纹，永不放行）
KNOWN_LEAKED = [
    "80a47d" + "7eae0bef204ccf4a2714c96bec8809",   # 旧 NCBI API key
    "ZWDasd" + "248655",                            # 旧 ECS root 口令
]

PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI 风格 API key"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"), "GitHub token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"), "私钥块"),
    (re.compile(r"(api[_-]?key|apikey|password|passwd|secret|token)\s*[=:]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']", re.I), "硬编码凭据赋值"),
    (re.compile(r"(?:\d{1,3}\.){3}\d{1,3}\s*\(?(?:密码|password|口令)", re.I), "IP+口令组合"),
    (re.compile(r"root@[\w.\-]+[: ]\s*\(?\s*密码", re.I), "root 明文口令"),
]


def main() -> int:
    hits = []
    for i, line in enumerate(sys.stdin.read().splitlines(), 1):
        if not line.startswith("+"):
            continue
        low = line.lower()
        if any(x in low for x in ("example", "placeholder", "your-api", "your_api",
                                  "xxx", "os.environ", "${", "environ.get", "占位")):
            continue
        for leaked in KNOWN_LEAKED:
            if leaked in line:
                hits.append(f"  [已泄露凭据指纹] {line.strip()[:120]}")
        for pat, label in PATTERNS:
            if pat.search(line):
                hits.append(f"  [{label}] {line.strip()[:120]}")
    if hits:
        seen = set()
        for h in hits:
            if h not in seen:
                print(h)
                seen.add(h)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
