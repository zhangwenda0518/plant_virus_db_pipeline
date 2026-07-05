#!/usr/bin/env python3
"""
补丁: 从 Olivar CSV 补全 all_primers.tsv 中 Olivar TILED 引物的位置和产物大小。
运行: python patch_olivar_positions.py ~/designed_primers
"""
import sys, re, csv
from pathlib import Path
import polars as pl

def main():
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("~/designed_primers").expanduser()
    tsv_file = base / "all_primers.tsv"
    olivar_dir = base / "olivar_tmp"
    if not tsv_file.exists():
        print(f"✗ 文件不存在: {tsv_file}"); return
    if not olivar_dir.exists():
        print(f"✗ Olivar 目录不存在: {olivar_dir}"); return

    print(f"加载 {tsv_file}...")
    df = pl.read_csv(tsv_file, separator='\t', ignore_errors=True)

    # 找到所有 Olivar TILED 行
    olivar_mask = (pl.col("Method") == "Olivar")
    olivar_rows = df.filter(olivar_mask)
    print(f"  Olivar 行: {len(olivar_rows)}")

    updated = 0

    # 方案: 遍历所有 Olivar CSV, 建立全局 (fP,rP)→(start,end) 索引
    print("  构建 Olivar 索引...")
    olivar_index = {}  # (fP.upper(), rP.upper()) -> (start, end)
    csv_count = 0
    for csv_path in olivar_dir.rglob("olivar-design.csv"):
        try:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    fp = str(row.get('fP', '')).strip()
                    rp = str(row.get('rP', '')).strip()
                    if fp and rp:
                        s = row.get('start', '') or row.get('insert_start', '')
                        e = row.get('end', '') or row.get('insert_end', '')
                        key = (fp.upper(), rp.upper())
                        if key not in olivar_index:  # 保留第一个匹配
                            olivar_index[key] = (s, e)
        except Exception:
            continue
        csv_count += 1
    print(f"  CSV 文件: {csv_count}, 索引条目: {len(olivar_index)}")

    # 匹配并更新 (逐行修改 DataFrame)
    for i in range(len(df)):
        if df[i, 'Method'] != 'Olivar':
            continue
        fwd = str(df[i, 'Fwd_Seq']).strip().upper()
        rev = str(df[i, 'Rev_Seq']).strip().upper()
        key = (fwd, rev)
        if key in olivar_index:
            s, e = olivar_index[key]
            prod = str(int(e) - int(s)) if s and e else "0"
            df[i, 'Fwd_Start'] = str(s)
            df[i, 'Rev_Start'] = str(e)
            df[i, 'Product'] = str(prod)
            updated += 1
        if (i + 1) % 20000 == 0:
            print(f"  ... {i+1}/{len(df)} (已更新 {updated})", flush=True)

    if updated > 0:
        # 备份
        bak = tsv_file.with_suffix('.tsv.bak')
        print(f"  备份 → {bak}")
        tsv_file.rename(bak)
        print(f"  写入 {tsv_file} ({updated} 行已更新)")
        df.write_csv(tsv_file, separator='\t')
    else:
        print("  无需更新")

if __name__ == "__main__":
    main()
