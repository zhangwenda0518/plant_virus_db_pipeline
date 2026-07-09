#!/usr/bin/env python3
"""从 DPV 数据库提取植物病毒症状图片"""
import os, re, json, pathlib

DPV_DIR = pathlib.Path(r"D:/桌面/NEBLab/rag-db/dpv_database")
MD_DIR = DPV_DIR / "md"
IMG_DIR = DPV_DIR / "images"
OUT_JSON = pathlib.Path(r"D:/桌面/C-host_classify/plant_virus_db_pipeline/docs/data/dpv_gallery.json")

# 症状关键词 (图片描述含这些词 → 症状图)
SYMPTOM_KEYWORDS = [
    'symptom', 'symptoms', 'mosaic', 'necrosis', 'necrotic', 'chlorosis', 'chlorotic',
    'leaf', 'leaves', 'plant', 'infected', 'inoculated', 'lesion', 'lesions',
    'blister', 'distortion', 'stunt', 'stunted', 'vein clearing', 'vein banding',
    'ringspot', 'streak', 'wilt', 'yellow', 'mottle', 'crinkle', 'leaf curl',
    'fruit', 'stem', 'flower', 'seed', 'pod', 'root', 'tuber',
    'systemic', 'local', 'field', 'greenhouse',
]

# 非症状关键词 (图片描述含这些词 → 非症状图)
NON_SYMPTOM_KEYWORDS = [
    'virion', 'particle', 'negatively stained', 'electron micrograph', 'micrograph',
    'crystal', 'model', 'genetic map', 'genome', 'RNA', 'subunit',
    'immunogold', 'probed', 'antibody', 'antiserum', 'western blot',
    'nucleotide', 'sequence', 'restriction', 'plasmid', 'vector',
    'diagram', 'schematic', 'drawing', 'graph', 'table',
    'bar is', 'bar=', 'nm', 'angstrom',
    'structural', 'structure of', 'X-ray', 'cryo',
    'inclusion', 'X-body', 'viroplasm', 'protoplast',
    'striposome', 'microtubule', 'ribosome',
]

def classify_figure(caption):
    """判断图片是否为植物病毒症状图"""
    cap_lower = caption.lower()

    # 先检查非症状关键词
    nonsymp_score = sum(1 for k in NON_SYMPTOM_KEYWORDS if k.lower() in cap_lower)
    if nonsymp_score >= 2:
        return 'other'

    # 检查症状关键词
    symp_score = sum(1 for k in SYMPTOM_KEYWORDS if k.lower() in cap_lower)
    if symp_score >= 2:
        return 'symptom'

    # 模糊情况
    if symp_score >= 1 and nonsymp_score == 0:
        return 'symptom'

    return 'other'


def extract_virus_name(filename):
    """从文件名推断病毒名: Tobacco_mosaic_virus_d370f01.jpg -> Tobacco mosaic virus"""
    name = filename.replace('_', ' ').lower()
    # Remove DPV code
    name = re.sub(r' d\d+f\d+.*', '', name)
    name = name.strip().title()
    return name


def parse_dpv_md(filepath):
    """解析 DPV markdown 文件"""
    with open(filepath, encoding='utf-8', errors='replace') as f:
        text = f.read()

    info = {
        'dpv_no': '',
        'family': '',
        'genus': '',
        'species': '',
        'acronym': '',
        'hosts': [],
        'figures': []
    }

    # Extract DPV number
    m = re.search(r'DPV NO:\s*(\d+)', text)
    if m: info['dpv_no'] = m.group(1)

    # Extract Family
    m = re.search(r'Family:\s*(.+)', text)
    if m: info['family'] = m.group(1).strip()

    # Extract Genus
    m = re.search(r'Genus:\s*(.+)', text)
    if m: info['genus'] = m.group(1).strip()

    # Extract Species/Acronym
    m = re.search(r'Species:\s*(.+?)\s*\|\s*Acronym:\s*(\w+)', text)
    if m:
        info['species'] = m.group(1).strip()
        info['acronym'] = m.group(2).strip()
    else:
        # Try just species
        m = re.search(r'Species:\s*(.+)', text)
        if m: info['species'] = m.group(1).strip()

    # Extract host plants from Host Range section
    host_section = re.search(r'Host Range.*?\n(.*?)(?=\n###|\n##)', text, re.DOTALL)
    if host_section:
        hosts_text = host_section.group(1)
        # Find italicized Latin names
        latin_names = re.findall(r'\*([A-Z][a-z]+ [a-z]+(?:\s+var\.\s+\w+)?)\*', hosts_text)
        info['hosts'] = list(set(latin_names))[:10]

    # Extract figures with captions
    fig_section = re.search(r'### Figures\n(.*?)(?=\n##|\Z)', text, re.DOTALL)
    if fig_section:
        figs_text = fig_section.group(1)
        # Pattern: [![dpv figure](../images/FILENAME.jpg)](...)
        # Followed by caption text
        img_pattern = re.finditer(
            r'\[!\[dpv figure\]\(\.\./images/([^)]+)\)\]\([^)]+\)\s*\n\n(.*?)(?=\n\n\[!|\n\n$|\Z)',
            figs_text, re.DOTALL
        )
        for m in img_pattern:
            filename = m.group(1)
            caption = m.group(2).strip().replace('\n', ' ')
            caption = re.sub(r'\[.*?\]\(.*?\)', '', caption)  # remove markdown links
            info['figures'].append({
                'filename': filename,
                'caption': caption,
                'type': classify_figure(caption)
            })

    return info


def main():
    all_photos = []
    stats = {'symptom': 0, 'other': 0, 'total_viruses': 0}

    for md_file in sorted(MD_DIR.glob('*.md')):
        info = parse_dpv_md(md_file)
        if not info['figures']:
            continue
        stats['total_viruses'] += 1

        for fig in info['figures']:
            if fig['type'] == 'symptom':
                stats['symptom'] += 1
            else:
                stats['other'] += 1

            # Build virus name in Latin form
            virus_name = info['species'] or extract_virus_name(fig['filename'])

            all_photos.append({
                'virus': virus_name,
                'virus_latin': virus_name,
                'virus_ictv': virus_name,
                'acronym': info['acronym'],
                'family': info['family'],
                'genus': info['genus'],
                'dpv_no': info['dpv_no'],
                'filename': fig['filename'],
                'caption': fig['caption'],
                'type': fig['type'],
                'hosts': info['hosts'],
                'img_path': f'../dpv_images/{fig["filename"]}'
            })

    # Write JSON
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(all_photos, f, ensure_ascii=False, indent=2)

    print(f"Total viruses: {stats['total_viruses']}")
    print(f"Symptom photos: {stats['symptom']}")
    print(f"Other photos: {stats['other']}")
    print(f"Total photos: {stats['symptom'] + stats['other']}")
    print(f"Output: {OUT_JSON}")

    # Show samples
    symptoms = [p for p in all_photos if p['type'] == 'symptom']
    print(f"\nSample symptom photos:")
    for p in symptoms[:5]:
        print(f"  [{p['virus']}] {p['caption'][:100]}")


if __name__ == '__main__':
    main()
