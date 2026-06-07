#!/usr/bin/env python3
"""
========================================================================
植物病毒引物设计全流程 — 总控脚本
========================================================================

一键运行从数据准备到 Web 部署的完整流程。

用法:
  # 完整流程
  python run_pipeline.py --full

  # 分步运行
  python run_pipeline.py --step prepare      # Step 0: 数据准备
  python run_pipeline.py --step fetch         # Step 1: 下载基因组
  python run_pipeline.py --step design        # Step 2: 设计引物
  python run_pipeline.py --step validate      # Step 3: 验证引物
  python run_pipeline.py --step database      # Step 4: 构建数据库
  python run_pipeline.py --step web           # Step 5: 启动 Web
"""

import argparse
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent


def run_step(step_name, script, args=None):
    """运行单个步骤"""
    script_path = BASE_DIR / script
    if not script_path.exists():
        print(f"✗ 脚本不存在: {script_path}")
        return False

    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)

    print(f"\n{'='*60}")
    print(f">>> 运行: {' '.join(cmd)}")
    print(f"{'='*60}")
    return subprocess.run(cmd).returncode == 0


def main():
    parser = argparse.ArgumentParser(description="植物病毒引物设计全流程")
    parser.add_argument("--full", action="store_true", help="运行完整流程")
    parser.add_argument("--step", choices=["prepare", "fetch", "design",
                        "validate", "database", "web"],
                        help="运行指定步骤")
    parser.add_argument("--threads", type=int, default=8, help="并行线程数")
    parser.add_argument("--skip-blast", action="store_true",
                        help="验证时跳过 BLAST")
    parser.add_argument("--quick-validate", action="store_true",
                        help="快速验证 (仅二聚体+GC)")
    parser.add_argument("--port", type=int, default=5000, help="Web 端口")
    args = parser.parse_args()

    steps = []

    if args.full:
        steps = ["prepare", "fetch", "design", "validate", "database", "web"]
    elif args.step:
        steps = [args.step]
    else:
        parser.print_help()
        print("\n请指定 --full 或 --step <步骤名>")
        return

    # 执行步骤
    for step in steps:
        if step == "prepare":
            if not run_step("Step 0: 数据准备", "step0_prepare_plants.py"):
                print("  ⚠ 数据准备失败, 继续...")

        elif step == "fetch":
            if not run_step("Step 1: 下载基因组", "step1_fetch_genomes.py",
                           ["--priority-only", "--limit", "10"]):
                print("  ⚠ 基因组下载部分失败")

        elif step == "design":
            if not run_step("Step 2: 设计引物", "step2_design_primers.py",
                           ["--threads", str(args.threads)]):
                print("  ⚠ 引物设计部分失败")

        elif step == "validate":
            val_args = []
            if args.skip_blast:
                val_args.append("--skip-blast")
            if args.quick_validate:
                val_args.append("--quick")
            run_step("Step 3: 验证引物", "step3_validate_primers.py", val_args)

        elif step == "database":
            run_step("Step 4: 构建数据库", "step4_build_database.py",
                    ["--force"])

        elif step == "web":
            print(f"\n{'='*60}")
            print(">>> 启动 Web 服务器...")
            print(f">>> 浏览器打开: http://localhost:{args.port}")
            print(f"{'='*60}")
            run_step("Step 5: Web 服务器", "step5_web_server.py",
                    ["--port", str(args.port)])

    print(f"\n{'='*60}")
    print("全流程完成!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
