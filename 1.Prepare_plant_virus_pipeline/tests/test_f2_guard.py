#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_f2_guard.py — F2 护栏验证（合成数据 + 真实快照黄金测试）

1) 合成数据：确认保护表达式的边界
   - RefSeq(NC_) + complete           → 受保护（不降级）
   - GenBank + complete               → 不受保护（照旧降级）
   - RefSeq + partial                 → 不受保护
   - 缺 Nuc_Completeness 列           → 不保护（保守，不改变原有行为）
   - PVDB_GUARDS=0                    → 保护表达式恒为 False（等价旧行为）
2) 真实快照黄金测试（若本机存在 $TEMP/All_Classified_snapshot.tsv 且 md5 匹配）：
   核对"基因级规则命中 2975 条、其中 307 条为 RefSeq+complete 受保护"，
   这些正是被误伤的完整参考序列（Cannabis cryptic virus / Pistacia emaravirus 等）。

运行：python tests/test_f2_guard.py -v
"""
import hashlib
import importlib.util
import os
import subprocess
import sys
import unittest

import polars as pl

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
F2_PATH = os.path.join(MOD, "F2_classify_segmented.py")
SNAP = os.path.join(os.environ.get("TEMP", "/tmp"), "All_Classified_snapshot.tsv")
SNAP_MD5 = "9cd4964dd766d815c0512a4d41533415"
GENE_RULE = (r"(?i)complete\s+cds|complete\s+coding|complete\s+genes?\b|\bgene\b|\bgenes\b")
NOT_GENE = r"(?i)complete\s+genome|complete\s+sequence|complete\s+segment"


def load_f2():
    spec = importlib.util.spec_from_file_location("f2_under_test", F2_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TestProtectionExpr(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f2 = load_f2()

    def test_default_on(self):
        self.assertTrue(self.f2._GUARDS_ON, "默认应开启护栏（PVDB_GUARDS 未设为 0）")

    def test_refseq_complete_is_protected(self):
        df = pl.DataFrame({
            "Accession": ["NC_077695.1", "MT334620.1", "NC_000001.1"],
            "Nuc_Completeness": ["complete", "complete", "partial"],
            "GenBank_Title": ["x", "y", "z"],
        })
        got = df.filter(self.f2.gene_rule_protection_expr(df.columns))["Accession"].to_list()
        self.assertEqual(got, ["NC_077695.1"])

    def test_missing_column_means_no_protection(self):
        df = pl.DataFrame({"Accession": ["NC_077695.1"], "GenBank_Title": ["x"]})
        self.assertEqual(df.filter(self.f2.gene_rule_protection_expr(df.columns)).height, 0)

    def test_rule_composition_matches_expected(self):
        """护栏只影响"基因级标题"那一条规则，不影响其它分支"""
        df = pl.DataFrame({
            "Accession": ["NC_1", "GB_1"],
            "Nuc_Completeness": ["complete", "complete"],
            "GenBank_Title": ["some virus gene, complete cds", "other virus gene, complete cds"],
        })
        t = pl.col("GenBank_Title").cast(pl.Utf8).str.to_lowercase()
        rule = t.str.contains(GENE_RULE) & ~t.str.contains(NOT_GENE)
        prot = self.f2.gene_rule_protection_expr(df.columns)
        self.assertEqual(df.filter(rule).height, 2)                # 规则本身命中 2 条
        self.assertEqual(df.filter(rule & ~prot).height, 1)        # 护栏挡下 1 条（NC_1）
        self.assertEqual(df.filter(rule & ~prot)["Accession"].to_list(), ["GB_1"])

    def test_guards_can_be_disabled_by_env(self):
        code = (
            "import importlib.util,sys,os;"
            f"spec=importlib.util.spec_from_file_location('f2', r'{F2_PATH}');"
            "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
            "import polars as pl;"
            "df=pl.DataFrame({'Accession':['NC_1'],'Nuc_Completeness':['complete']});"
            "print('GUARDS', m._GUARDS_ON, 'PROTECTED', df.filter(m.gene_rule_protection_expr(df.columns)).height)"
        )
        env = dict(os.environ, PVDB_GUARDS="0")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
        self.assertIn("GUARDS False", out.stdout, out.stderr)
        self.assertIn("PROTECTED 0", out.stdout)


class TestGoldenSnapshot(unittest.TestCase):
    """真实数据黄金测试：核对护栏在 2026-09-28 的分类快照上的作用面"""

    def setUp(self):
        if not os.path.isfile(SNAP):
            self.skipTest(f"缺少快照 {SNAP}（可从服务器 F-dedup/split_results/ 取）")
        with open(SNAP, "rb") as fh:
            if hashlib.md5(fh.read()).hexdigest() != SNAP_MD5:
                self.skipTest("快照内容与记录不符（md5 不一致），跳过黄金测试")

    def test_guard_scope_on_real_snapshot(self):
        f2 = load_f2()
        df = pl.read_csv(SNAP, separator="\t", infer_schema_length=0, truncate_ragged_lines=True)
        t = pl.col("GenBank_Title").cast(pl.Utf8).fill_null("").str.to_lowercase()
        rule = t.str.contains(GENE_RULE) & ~t.str.contains(NOT_GENE)
        prot = f2.gene_rule_protection_expr(df.columns)
        flagged = df.filter(rule)
        pin = df.filter(rule & prot)
        self.assertEqual(df.height, 8889)
        self.assertEqual(flagged.height, 2975)
        self.assertEqual(pin.height, 307, "被护栏救回的 RefSeq 完整基因组条数")
        # 受保护记录必须全部是 RefSeq 且 complete，否则护栏开得太宽
        self.assertEqual(pin.filter(~pl.col("Accession").str.starts_with("NC_")).height, 0)
        self.assertEqual(
            pin.filter(pl.col("Nuc_Completeness").cast(pl.Utf8).str.to_lowercase() != "complete").height, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
