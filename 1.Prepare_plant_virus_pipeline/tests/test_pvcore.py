#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pvcore.py — 纯离线单测（unittest，无需 pytest、不碰真实数据）

覆盖 pvcore 的四类关键行为：
1. 计数函数在文件缺失时返回 None（绝不返回 0，防止"静默 0"）
2. find_existing 的候选名回退（文件改名后的向前兼容）
3. 三个护栏：VMR 植物权威 / RefSeq 完整基因组 / 长度离群
4. 账本与隔离目录、manifest 往返与新鲜度检测

运行：python tests/test_pvcore.py -v
"""
import json
import os
import sys
import tempfile
import unittest

import polars as pl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
import pvcore as P                     # noqa: E402


def make_df(**cols):
    return pl.DataFrame(dict(cols))


class TestCounters(unittest.TestCase):
    def test_missing_returns_none_not_zero(self):
        self.assertIsNone(P.count_rows("no/such/file.tsv"))
        self.assertIsNone(P.count_fasta("no/such/file.fasta"))
        self.assertIsNone(P.md5("no/such/file"))

    def test_counts(self):
        with tempfile.TemporaryDirectory() as d:
            tsv = os.path.join(d, "a.tsv")
            with open(tsv, "w", encoding="utf-8") as f:
                f.write("h1\th2\n1\t2\n3\t4\n")
            self.assertEqual(P.count_rows(tsv), 2)
            fa = os.path.join(d, "a.fasta")
            with open(fa, "w", encoding="utf-8") as f:
                f.write(">x\nACGT\n>y\nTTTT\n")
            self.assertEqual(P.count_fasta(fa), 2)

    def test_find_existing_prefers_first(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.path.join(d, "old.tsv")
            new = os.path.join(d, "new.tsv")
            open(old, "w").close()
            open(new, "w").close()
            self.assertEqual(P.find_existing([new, old]), new)
            os.remove(new)
            self.assertEqual(P.find_existing([new, old]), old)
            self.assertIsNone(P.find_existing([new]))
            with self.assertRaises(FileNotFoundError):
                P.find_existing([new], required=True)


class TestGuards(unittest.TestCase):
    def test_vmr_says_plant_rescues_cacao(self):
        """zetainfla 事故：VMR 说 plants 的物种不该被当非植物删掉"""
        removed = make_df(
            Accession=["NC_038379.1", "NC_040365.1"],
            Taxid=["1960254", "2293307"],
            **{"Host source": ["plants", "invertebrates"],
               "VMR_Family": ["Caulimoviridae", "Anicreviridae"],
               "Species_ICTV": ["Badnavirus zetainflatheobromae",
                                "Ketkevirus silauonis"]})
        rescued = P.guard_vmr_says_plant(removed, plant_families={"Caulimoviridae"})
        self.assertEqual(rescued["Accession"].to_list(), ["NC_038379.1"])

    def test_refseq_complete_rescued(self):
        """F2 事故：RefSeq + complete + 长度正常 → 不该被判成 CDS_Fragment"""
        removed = make_df(
            Accession=["NC_075086.1", "NC_076289.1", "MT334620.1"],
            Nuc_Completeness=["complete", "complete", "complete"],
            VMR_Genus=["Mastrevirus", "Alphacytorhabdovirus", "Potyvirus"],
            Length=["2739", "13875", "9800"])
        lens = {"Mastrevirus": {"median": 2800, "p25": 2700, "p75": 2900},
                "Alphacytorhabdovirus": {"median": 13500, "p25": 13000, "p75": 14000},
                "Potyvirus": {"median": 9700, "p25": 9500, "p75": 9900}}
        rescued = P.guard_refseq_complete(removed, lens)
        self.assertEqual(sorted(rescued["Accession"].to_list()),
                         ["NC_075086.1", "NC_076289.1"])   # 非 RefSeq 的不救

    def test_refseq_complete_skips_partial(self):
        removed = make_df(Accession=["NC_000001.1"], Nuc_Completeness=["partial"],
                          VMR_Genus=["Potyvirus"], Length=["9800"])
        self.assertEqual(P.guard_refseq_complete(removed, {}).height, 0)

    def test_length_outlier_flags_13kb_badnavirus(self):
        df = make_df(Accession=["NC_038379.1", "NC_076048.1"],
                     VMR_Genus=["Badnavirus", "Badnavirus"],
                     Length=["13221", "7297"])
        lens = {"Badnavirus": {"median": 7400, "p25": 7200, "p75": 7600}}
        hits = P.guard_length_outlier(df, lens)
        self.assertEqual(hits["Accession"].to_list(), ["NC_038379.1"])

    def test_guards_tolerate_empty_input(self):
        empty = make_df(Accession=[], Nuc_Completeness=[], VMR_Genus=[], Length=[])
        for g in (P.guard_vmr_says_plant(empty, set()),
                  P.guard_refseq_complete(empty, {}),
                  P.guard_length_outlier(empty, {})):
            self.assertEqual(g.height, 0)


class TestLedgerAndQuarantine(unittest.TestCase):
    def test_ledger_and_quarantine(self):
        with tempfile.TemporaryDirectory() as d:
            led = P.Ledger(d)
            df = make_df(Accession=["A1", "A2"], Species_ICTV=["x", "y"])
            self.assertEqual(led.add("L1_kingdom", "界不符", df), 2)
            led.add("L0", "无命中", df.head(0))
            path = led.write()
            self.assertTrue(os.path.isfile(path))
            rows = P.read_tsv(path)
            self.assertEqual(rows.height, 2)
            self.assertEqual(led.total(), 2)
            q = P.quarantine(df, d, "guard_vmr", "救回 2 条")
            self.assertTrue(os.path.isfile(q))
            self.assertEqual(P.count_rows(q), 2)


class TestManifest(unittest.TestCase):
    def test_manifest_roundtrip_and_freshness(self):
        with tempfile.TemporaryDirectory() as d:
            inp = os.path.join(d, "in.tsv")
            with open(inp, "w", encoding="utf-8") as f:
                f.write("a\tb\n1\t2\n")
            out = os.path.join(d, "out.tsv")
            with open(out, "w", encoding="utf-8") as f:
                f.write("a\n9\n")
            P.write_manifest(d, outputs=[out], inputs=[inp], params={"ani": 0.98}, script="test")
            man = P.read_manifest(d)
            self.assertEqual(man["params"]["ani"], 0.98)
            self.assertEqual(man["outputs"][out]["rows"], 1)
            self.assertEqual(P.check_freshness(d), [])          # 输入未变 → 新鲜
            with open(inp, "a", encoding="utf-8") as f:
                f.write("3\t4\n")
            self.assertTrue(P.check_freshness(d))               # 输入变了 → 报警

    def test_missing_manifest_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(P.check_freshness(d))

    def test_genus_lengths_and_plant_families_graceful(self):
        self.assertEqual(P.load_genus_lengths("no/such.tsv"), {})
        self.assertEqual(P.load_plant_families("no/such.xlsx"), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
