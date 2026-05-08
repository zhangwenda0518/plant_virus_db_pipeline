import csv
import os
import argparse
import shutil

def main():
    # 设置命令行参数解析
    parser = argparse.ArgumentParser(description="基于 Accession 合并信息并检查 Title 和 Length 的一致性。")
    parser.add_argument("-s", "--seq", default="sequence_info.tsv", help="输入文件1：包含序列信息的 sequence_info.tsv")
    parser.add_argument("-p", "--plant", default="Plant_Virus_Info.tsv", help="输入文件2：需要被补充信息的 Plant_Virus_Info.tsv")
    parser.add_argument("-o", "--output", help="输出文件。如果不指定，则直接覆盖原 Plant_Virus_Info.tsv 文件")
    parser.add_argument("-l", "--log", default="consistency_check.log", help="一致性检测日志文件")
    
    args = parser.parse_args()
    
    seq_file = args.seq
    plant_file = args.plant
    # 如果没有提供输出文件，则先写入一个临时文件，稍后替换原文件
    out_file = args.output if args.output else plant_file + ".tmp"
    log_file = args.log

    if not os.path.exists(seq_file) or not os.path.exists(plant_file):
        print(f"❌ 错误: 找不到输入文件，请检查 '{seq_file}' 和 '{plant_file}' 是否在当前目录下。")
        return

    # 1. 基于 Accession 读取 sequence_info.tsv
    seq_data = {}
    with open(seq_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            acc = row.get('Accession', '').strip()
            if acc: # 确保 Accession 不为空
                seq_data[acc] = {k.strip(): v.strip() for k, v in row.items() if k}

    # 2. 读取并处理 Plant_Virus_Info.tsv
    with open(plant_file, 'r', encoding='utf-8') as fin, \
         open(out_file, 'w', encoding='utf-8', newline='') as fout, \
         open(log_file, 'w', encoding='utf-8') as flog:
        
        reader = csv.DictReader(fin, delimiter='\t')
        fieldnames = [field.strip() for field in reader.fieldnames if field]
        
        # 重新排列列名：在 Molecule_type 前加 Topology，在它后面加 Molecule_Type2
        if 'Molecule_type' in fieldnames:
            mol_idx = fieldnames.index('Molecule_type')
            new_fieldnames = fieldnames[:mol_idx] + ['Topology', 'Molecule_type', 'Molecule_Type2'] + fieldnames[mol_idx+1:]
        else:
            # 万一没找到，直接加在最后
            new_fieldnames = fieldnames + ['Topology', 'Molecule_Type2']
            
        writer = csv.DictWriter(fout, fieldnames=new_fieldnames, delimiter='\t')
        writer.writeheader()
        
        for row in reader:
            # 清理当前行数据，去除多余空格
            row = {k.strip(): v.strip() if v else '' for k, v in row.items() if k}
            acc = row.get('Accession', '')
            
            if acc in seq_data:
                s_data = seq_data[acc]
                
                # --- 一致性比对并写入日志 (已移除 Molecule_type 的检查) ---
                if row.get('GenBank_Title') != s_data.get('Title'):
                    flog.write(f"[{acc}] Title 不一致:\n  Plant_DB: {row.get('GenBank_Title')}\n  Seq_Info: {s_data.get('Title')}\n\n")
                
                if row.get('Length') != s_data.get('Length'):
                    flog.write(f"[{acc}] Length 不一致:\n  Plant_DB: {row.get('Length')}\n  Seq_Info: {s_data.get('Length')}\n\n")
                
                # --- 添加新列的信息 ---
                row['Topology'] = s_data.get('Topology', 'Unknown')
                row['Molecule_Type2'] = s_data.get('Molecule_Type', 'Unknown')
            else:
                row['Topology'] = 'Not_Found'
                row['Molecule_Type2'] = 'Not_Found'
                flog.write(f"[{acc}] 警告: 在 {seq_file} 中未找到该 Accession 的信息\n\n")
                
            writer.writerow(row)

    # 3. 处理输出文件逻辑
    if not args.output:
        # 如果没有指定输出文件，将临时文件覆盖原文件
        shutil.move(out_file, plant_file)
        print(f"✅ 处理完成！已直接在原文件 \033[92m{plant_file}\033[0m 中添加了信息。")
    else:
        print(f"✅ 处理完成！生成了包含新信息的文件：\033[92m{args.output}\033[0m")
        
    print(f"👉 一致性比对结果 (仅含 Title 和 Length) 已保存至：\033[96m{log_file}\033[0m")

if __name__ == "__main__":
    main()
