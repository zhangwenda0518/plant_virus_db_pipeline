import polars as pl
import subprocess
import tempfile
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
import json
import time
import sys

class ParallelTaxonKitProcessor:
    """并行化的taxonkit处理器"""
    
    @staticmethod
    def process_taxid_batch(args):
        """处理一批taxid的静态方法（用于多进程）"""
        taxid_batch, taxonkit_path, data_dir = args
        
        # 过滤空值
        taxid_batch = [str(t).strip() for t in taxid_batch if t is not None and str(t).strip() != '']
        if not taxid_batch:
            return {}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            tmp_path = f.name
            f.write('\n'.join(taxid_batch))
        
        try:
            cmd = [taxonkit_path, "lineage"]
            if data_dir:
                cmd.extend(["--data-dir", data_dir])
            
            cmd.extend(["--threads", "2", tmp_path])
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            lineage_dict = {}
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split('\t')
                
                if len(parts) >= 2:
                    taxid = parts[0].strip()
                    if not taxid:
                        continue
                    lineage = parts[1].strip()
                    lineage_dict[taxid] = lineage
            
            return lineage_dict
        except subprocess.CalledProcessError as e:
            print(f"⚠ taxonkit批处理错误: {e.stderr[:200] if e.stderr else str(e)}")
            return {}
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def __init__(self, taxonkit_path="taxonkit", data_dir=None, num_processes=None):
        self.taxonkit_path = taxonkit_path
        self.data_dir = data_dir
        self.num_processes = num_processes or max(1, mp.cpu_count() // 2)
        self.cache = {}
        self.cache_file = "taxid_lineage_cache.json"
        self._load_cache()
    
    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                print(f"✓ 已加载缓存，包含 {len(self.cache)} 个taxid")
            except Exception as e:
                print(f"⚠ 无法加载缓存: {e}")
    
    def _save_cache(self):
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            print(f"⚠ 无法保存缓存: {e}")
    
    def get_lineage_parallel(self, taxids: pl.Series) -> pl.Series:
        taxids_str = taxids.cast(pl.Utf8).fill_null("")
        
        unique_taxids = (
            taxids_str.filter(taxids_str.str.len_chars() > 0)
            .unique()
            .to_list()
        )
        
        if not unique_taxids:
            return pl.Series("", [""] * len(taxids), dtype=pl.Utf8)
        
        print(f"📊 需要处理 {len(unique_taxids)} 个唯一Taxid")
        
        uncached = [t for t in unique_taxids if t not in self.cache and t != ""]
        print(f"📊 其中 {len(uncached)} 个未缓存")
        
        if uncached:
            batch_size = 50000
            batches = []
            
            for i in range(0, len(uncached), batch_size):
                batch = uncached[i:i + batch_size]
                batches.append((batch, self.taxonkit_path, self.data_dir))
            
            print(f"🔄 使用 {self.num_processes} 个进程并行处理...")
            
            with ProcessPoolExecutor(max_workers=self.num_processes) as executor:
                future_to_batch = {
                    executor.submit(self.process_taxid_batch, batch): i
                    for i, batch in enumerate(batches)
                }
                
                completed = 0
                for future in as_completed(future_to_batch):
                    try:
                        batch_result = future.result()
                        self.cache.update(batch_result)
                        completed += 1
                        print(f"✅ 完成 {completed}/{len(batches)} 批，累计缓存 {len(self.cache)} 个taxid")
                    except Exception as e:
                        print(f"❌ 批处理失败: {e}")
            
            self._save_cache()
        
        # 优化点：使用原生的 replace 替代极其缓慢的 map_elements (速度提升十倍以上)
        result_series = taxids_str.replace(self.cache, default="")
        return result_series

def preprocess_data(input_file: str, bad_file: str) -> str:
    """预清洗数据：分离坏行、保留坏行的Accession、输出绝对纯净的临时文件"""
    print(f"🧹 开始预清洗数据，扫描损坏行...")
    temp_clean_file = input_file + ".clean_tmp.tsv"
    
    total_lines = 0
    bad_lines = 0
    
    # 优化点：使用 'utf-8-sig' 自动去除某些文件可能携带的 BOM 头 (\ufeff)
    with open(input_file, 'r', encoding='utf-8-sig', errors='ignore') as fin, \
         open(temp_clean_file, 'w', encoding='utf-8') as fclean, \
         open(bad_file, 'w', encoding='utf-8') as fbad:
        
        # 处理表头
        header_line = fin.readline()
        fclean.write(header_line)
        fbad.write(header_line)
        
        headers = [h.strip().lstrip('#') for h in header_line.strip().split('\t')]
        expected_cols = len(headers)
        
        for line in fin:
            total_lines += 1
            clean_str = line.strip('\n')
            cols = clean_str.split('\t')
            
            # 判断是否为坏行
            is_bad = False
            if len(cols) != expected_cols:
                is_bad = True
            elif '#Accession' in clean_str or 'Taxid' in clean_str:
                is_bad = True
                
            if not is_bad:
                fclean.write(line)
            else:
                bad_lines += 1
                fbad.write(line)
                
                # 尝试从坏行中提取 Accession
                first_col = cols[0].strip()
                match = re.search(r'^([A-Za-z0-9_.]+)', first_col)
                acc = match.group(1) if match else first_col.split(' ')[0]
                
                # 构造修复行：保留 Accession，后续所有列全置为空
                fixed_cols = [acc] + [""] * (expected_cols - 1)
                fclean.write('\t'.join(fixed_cols) + '\n')
                
    print(f"✅ 预清洗完成！")
    print(f"   - 总扫描行数: {total_lines:,}")
    print(f"   - 发现并隔离坏行: {bad_lines:,} 行 (已保存至 {bad_file})")
    print(f"   - 坏行处理策略: 已保留Accession，清空其他字段防止列错位。")
    
    return temp_clean_file, headers


def process_with_polars_optimized(input_file: str, output_file: str, bad_file: str, processes: int = 16, taxonkit_path: str = "taxonkit", data_dir: str = None):
    """优化的Polars处理流程"""
    print("🚀 启动优化的Polars处理流程")
    start_time = time.time()
    
    # 第一步：进行物理级预清洗
    temp_clean_file, headers = preprocess_data(input_file, bad_file)
    
    # 修复Bug：将 taxonkit_path 和 data_dir 传入实例化对象
    processor = ParallelTaxonKitProcessor(
        taxonkit_path=taxonkit_path,
        data_dir=data_dir,
        num_processes=processes
    )
    
    print("📊 读取并解析纯净数据文件...")
    try:
        # 优化点：现代Polars使用 infer_schema=False 代替 deprecated的 infer_schema_length=0
        # 兼容处理：在极少数旧版本中可能不支持 infer_schema=False，所以提供一个 schema 兜底策略最为稳妥
        schema_dict = {col: pl.String for col in headers}
        
        df = pl.read_csv(
            temp_clean_file,
            separator="\t",
            has_header=False,
            skip_rows=1,                   
            new_columns=headers,           
            schema_overrides=schema_dict,  # 强制全转为字符串，最安全的做法
            quote_char=None,               # 绝对关键：禁用引号解析！防止5'UTR等破坏制表符
            truncate_ragged_lines=False,   
            ignore_errors=False,           
            null_values=["", "NA", "null", "NULL", "-"]
        )
        
        if "taxid" in df.columns and "Taxid" not in df.columns:
            df = df.rename({"taxid": "Taxid"})
            
        print(f"📊 读取完成，共 {df.height:,} 行")
        
    except Exception as e:
        print(f"❌ 数据读取阶段遭遇严重失败: {e}")
        sys.exit(1)
    finally:
        # 删除临时清理文件释放空间
        if os.path.exists(temp_clean_file):
            os.remove(temp_clean_file)
    
    # 检查必要的列是否存在
    required_columns = ["Taxid", "Host_Taxid"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"❌ 缺少必要的列: {missing_columns} (请检查输入文件的表头大小写)")
        sys.exit(1)
    
    print("🦠 获取Virus_lineage...")
    virus_start = time.time()
    virus_lineage = processor.get_lineage_parallel(df["Taxid"])
    print(f"⏱ Virus_lineage耗时: {time.time() - virus_start:.2f}秒")
    
    print("🐄 获取Host_lineage...")
    host_start = time.time()
    host_lineage = processor.get_lineage_parallel(df["Host_Taxid"])
    print(f"⏱ Host_lineage耗时: {time.time() - host_start:.2f}秒")
    
    print("➕ 添加新列并重排顺序...")
    df = df.with_columns([
        virus_lineage.alias("Virus_lineage"),
        host_lineage.alias("Host_lineage")
    ])
    
    base_cols = [c for c in df.columns if c not in ["Virus_lineage", "Host_lineage"]]
    final_cols = []
    
    for col in base_cols:
        final_cols.append(col)
        if col == "Taxid":
            final_cols.append("Virus_lineage")
        elif col == "Host_Taxid":
            final_cols.append("Host_lineage")
            
    # 防止因为大小写等原因未插入成功，做兜底附加
    for col in ["Virus_lineage", "Host_lineage"]:
        if col not in final_cols:
            final_cols.append(col)
            
    df = df.select(final_cols)
    
    print("💾 写入输出文件...")
    write_start = time.time()
    
    df.write_csv(
        output_file, 
        separator="\t",
        include_header=True,
        quote_style="never"  # 输出也不带引号，保持纯净TSV格式
    )
    
    write_time = time.time() - write_start
    print(f"⏱ 写入耗时: {write_time:.2f}秒")
    
    total_time = time.time() - start_time
    print(f"\n✅ 处理完成!")
    print(f"📊 总行数: {df.height:,}")
    print(f"⏱ 总耗时: {total_time:.2f}秒 ({total_time/60:.2f}分钟)")
    print(f"📁 输出文件: {output_file}")
    print(f"🗑️ 坏行记录文件: {bad_file}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="使用Polars和taxonkit处理VHostMetadata文件，添加lineage信息，自动隔离并修复坏行",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("input", help="输入TSV文件路径")
    parser.add_argument("-o", "--output", default="VHostMetadata_with_lineage.tsv", help="输出文件路径")
    parser.add_argument("-b", "--bad-file", default="bad_rows_log.tsv", help="分离出损坏数据的保存路径 (默认: bad_rows_log.tsv)")
    parser.add_argument("--taxonkit", default="taxonkit", help="taxonkit可执行文件路径")
    parser.add_argument("--data-dir", default=None, help="taxonkit数据目录")
    parser.add_argument("--processes", type=int, default=None, help="并行进程数")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"❌ 输入文件不存在: {args.input}")
        sys.exit(1)
    
    # 修复Bug：新增 taxonkit_path 和 data_dir 参数传递
    process_with_polars_optimized(
        input_file=args.input,
        output_file=args.output,
        bad_file=args.bad_file,
        processes=args.processes or max(1, mp.cpu_count() // 2),
        taxonkit_path=args.taxonkit,
        data_dir=args.data_dir
    )

if __name__ == "__main__":
    main()
