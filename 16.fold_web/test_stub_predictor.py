# -*- coding: utf-8 -*-
"""测试桩：模拟 colabfold_batch 行为（为每个输入序列产出 rank_001 PDB + scores json）。
仅用于 fold_web 队列/入库链路的沙箱测试，不做真实预测。用法：
  python test_stub_predictor.py <input.fasta> <output_dir>
"""
import json
import sys
from pathlib import Path

inp, out = Path(sys.argv[1]), Path(sys.argv[2])
seqs, acc = {}, None
for line in open(inp, encoding="utf-8"):
    if line.startswith(">"):
        acc = line[1:].split()[0].strip()
        seqs[acc] = []
    elif acc:
        seqs[acc].append(line.strip())

for a, lines in seqs.items():
    seq = "".join(lines)
    d = out / a
    d.mkdir(parents=True, exist_ok=True)
    pdb = d / f"{a}_unrelaxed_rank_001_alphafold2_ptm_model_1_seed_000.pdb"
    with open(pdb, "w", encoding="utf-8") as f:
        for i, aa in enumerate(seq, 1):
            x = i * 1.5
            f.write(f"ATOM  {i:5d}  CA  ALA A{i:4d}      {x:8.3f}{i%7:8.3f}{i%5:8.3f}  1.00 {70+i%30:5.2f}           C\n")
        f.write("END\n")
    (d / f"{a}_scores_rank_001_alphafold2_ptm_model_1_seed_000.json").write_text(
        json.dumps({"mean_plddt": 72.5, "n_residues": len(seq)}), encoding="utf-8")
print(f"stub predicted {len(seqs)}")
