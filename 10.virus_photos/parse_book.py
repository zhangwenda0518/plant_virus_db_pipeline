#!/usr/bin/env python3
"""
解析《100种常见植物病毒病害彩色图鉴》，提取：
- 宿主植物 (中文名、拉丁名、科属)
- 病毒名称列表
- 病症描述
- 关联图片编号
"""

import re, json, os
from docx import Document
from collections import OrderedDict

DOCX = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\15587070.docx"
OUTPUT = r"D:\桌面\C-host_classify\plant_virus_db_pipeline\10.virus_photos\extracted\parsed_entries.tsv"

doc = Document(DOCX)

# Collect all non-empty paragraphs
paragraphs = [(i, p.text.strip()) for i, p in enumerate(doc.paragraphs) if p.text.strip()]

# Parse entries
entries = []
current_entry = None
current_family = ""
current_family_latin = ""

for idx, text in paragraphs:
    # Family header: "一、菊科" or similar pattern
    fm = re.match(r'^[一二三四五六七八九十]+、(.+科)', text)
    if fm:
        current_family = fm.group(1)
        # Next paragraph should have 科拉丁名
        continue

    # Family Latin name
    fm2 = re.match(r'^科拉丁名[：:]\s*(.+)', text)
    if fm2:
        current_family_latin = fm2.group(1)

    # Genus header: "(一)松果菊属(属拉丁名：Echinacea)"
    fm3 = re.match(r'^\([一二三四五六七八九十百]+\)\s*(.+?属)', text)
    if fm3 and '(' not in text[:10]:  # avoid matching species entries
        if current_entry:
            entries.append(current_entry)
        genus_part = fm3.group(1)
        genus_cn = re.sub(r'\(属拉丁名[：:].*', '', genus_part).strip().rstrip('）)')
        genus_latin = re.search(r'属拉丁名[：:]\s*(.+?)\)?$', genus_part)
        current_entry = {
            "family_cn": current_family,
            "family_latin": current_family_latin,
            "genus_cn": genus_cn,
            "genus_latin": genus_latin.group(1).strip() if genus_latin else "",
            "entry_num": 0,
            "species_cn": "",
            "species_latin": "",
            "description": "",
            "virus_text": "",
            "viruses": [],
            "figures": [],
            "symptoms": ""
        }
        continue

    # Species entry: "1.松果菊(种拉丁名：Echinacea purpurea)"
    if current_entry is not None:
        fm4 = re.match(r'^(\d+)\.\s*(.+?)(?:\(种拉丁名[：:]\s*(.+?)\))?$', text)
        if fm4 and '属' not in text:
            num = int(fm4.group(1))
            sp_cn = fm4.group(2).strip().rstrip('）)')
            sp_latin = fm4.group(3).strip().rstrip('）)') if fm4.group(3) else ""
            if num >= 1 and num <= 100 and len(sp_cn) >= 2:
                current_entry["entry_num"] = num
                current_entry["species_cn"] = sp_cn
                current_entry["species_latin"] = sp_latin
            continue

        # Host description (long paragraph after species name)
        if current_entry["entry_num"] > 0 and not current_entry["description"] and len(text) > 80 and "图" not in text and "编者在" not in text[:5] and "目前" not in text[:5] and "有关" not in text[:5]:
            current_entry["description"] = text
            continue

        # Virus disease description
        if current_entry["entry_num"] > 0 and current_entry["description"] and not current_entry["virus_text"]:
            current_entry["virus_text"] = text
            # Extract virus names
            virus_patterns = [
                r'([A-Z][a-z]+(?:\s+[a-z]+){1,5}\s+virus)',
                r'\(([A-Z]{2,}\d*)\)',
                r'\(([a-z]+\s+[a-z]+\s+[a-z]+\s+virus,\s*[A-Z]+)\)',
            ]
            viruses = set()
            for pat in virus_patterns:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    v = m.group(1).strip()
                    if len(v) > 3:
                        viruses.add(v)
            # Also match Chinese virus names
            cn_virus = re.findall(r'([\u4e00-\u9fff]{3,8}(?:花叶|黄脉|曲叶|斑驳|坏死|条纹|矮缩|丛枝|皱缩|黄化|卷叶|畸形|脉明)(?:病毒|病))', text)
            viruses.update(cn_virus)
            current_entry["viruses"] = list(viruses)[:15]

            # Extract symptom description
            symptom_patterns = re.findall(r'(发病初期[^。；]+[。；])', text)
            if not symptom_patterns:
                symptom_patterns = re.findall(r'(感病[^。；]+[。；])', text)
            if not symptom_patterns:
                symptom_patterns = re.findall(r'(典型[^。；]+[。；])', text)
            current_entry["symptoms"] = ' '.join(symptom_patterns[:3])
            continue

        # Figure reference
        fm5 = re.match(r'图\s*(\d+)\s+', text)
        if fm5 and current_entry["entry_num"] > 0:
            fig_num = int(fm5.group(1))
            fig_text = text
            current_entry["figures"].append({"num": fig_num, "caption": fig_text})
            continue

# Save last entry
if current_entry and current_entry["entry_num"] > 0:
    entries.append(current_entry)

# Output
print(f"Parsed {len(entries)} entries")

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write("\t".join(["EntryNum", "Species_CN", "Species_Latin", "Genus_CN", "Genus_Latin",
                       "Family_CN", "Family_Latin", "DiseaseName", "Viruses", "Symptoms",
                       "Figures", "Description"]) + "\n")
    for e in entries:
        f.write("\t".join([
            str(e["entry_num"]),
            e["species_cn"],
            e["species_latin"],
            e["genus_cn"],
            e["genus_latin"],
            e["family_cn"],
            e["family_latin"],
            "",
            "; ".join(e["viruses"]),
            e["symptoms"],
            str(len(e["figures"])),
            e["description"][:200]
        ]) + "\n")

# Print summary
for e in entries:
    virus_str = "; ".join(e["viruses"][:5])
    print(f"[{e['entry_num']:3d}] {e['species_cn']:<10s} | {e['genus_cn']:<8s} | {e['family_cn']:<6s} | Viruses: {len(e['viruses']):2d} | Figs: {len(e['figures'])} | {virus_str[:80]}")

print(f"\nTotal: {len(entries)} entries -> {OUTPUT}")
