"""Add validated NLR-virus-effector interactions to gene atlas"""
import json, os, re

outdir = os.path.dirname(__file__) + "/data"


def write_gene_data_js(outdir, updates):
    """Merge var declarations into data/gene_data.js, preserving any variables
    written by other scripts (e.g. ANTIVIRAL_NLR_DATA from build_gene_browser.py)
    and their declaration order.  Prevents the 4-vars-vs-5-vars overwrite bug."""
    path = os.path.join(outdir, "gene_data.js")
    existing, order = {}, []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^var\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*);\s*$', line)
                if m:
                    if m.group(1) not in existing:
                        order.append(m.group(1))
                    existing[m.group(1)] = m.group(2)
    for name, value in updates.items():
        if name not in existing:
            order.append(name)
        existing[name] = value
    with open(path, "w", encoding="utf-8") as f:
        for name in order:
            f.write("var " + name + " = " + existing[name] + ";\n")

nlr_virus_map = {
    'N':       {'virus':'Tobacco mosaic virus (TMV)','effector':'Replicase','nlr_type':'TIR-NB-LRR','plant':'Nicotiana tabacum'},
    'Nprime':  {'virus':'TMV','effector':'Coat protein (CP)','nlr_type':'CC-NB-LRR','plant':'Nicotiana tabacum'},
    'Rx':      {'virus':'Potato virus X (PVX)','effector':'CP','nlr_type':'CC-NB-LRR','plant':'Solanum tuberosum'},
    'Rx1':     {'virus':'PVX','effector':'CP','nlr_type':'CC-NB-LRR','plant':'Solanum tuberosum'},
    'Rx2':     {'virus':'PVX','effector':'CP','nlr_type':'CC-NB-LRR','plant':'Solanum tuberosum'},
    'Y-1':     {'virus':'Potato virus Y (PVY)','effector':'NIa','nlr_type':'CC-NB-LRR','plant':'Solanum tuberosum'},
    'Ry_sto':  {'virus':'PVY','effector':'CP','nlr_type':'TIR-NB-LRR','plant':'Solanum tuberosum'},
    'HRT':     {'virus':'Turnip crinkle virus (TCV)','effector':'CP','nlr_type':'CC-NB-LRR','plant':'Arabidopsis thaliana'},
    'RCY1':    {'virus':'Cucumber mosaic virus (CMV)','effector':'CP','nlr_type':'CC-NB-LRR','plant':'Arabidopsis thaliana'},
    'Tm-2':    {'virus':'Tomato mosaic virus (ToMV)','effector':'Movement protein (MP)','nlr_type':'CC-NB-LRR','plant':'Solanum lycopersicum'},
    'Tm-2a':   {'virus':'ToMV','effector':'MP','nlr_type':'CC-NB-LRR','plant':'Solanum lycopersicum'},
    'Sw-5b':   {'virus':'Tomato spotted wilt virus (TSWV)','effector':'MP','nlr_type':'CC-NB-LRR','plant':'Solanum lycopersicum'},
    'Prv':     {'virus':'Papaya ringspot virus (PRSV)','effector':'-','nlr_type':'TIR-NB-LRR','plant':'Cucumis melo'},
    'BSR1':    {'virus':'Barley stripe mosaic virus (BSMV)','effector':'MP','nlr_type':'CC-NB-LRR','plant':'Brachypodium distachyon'},
    'Ym2':     {'virus':'Wheat yellow mosaic virus (WYMV)','effector':'-','nlr_type':'CC-NB-LRR','plant':'Triticum aestivum'},
    'RT4-4':   {'virus':'CMV','effector':'2a','nlr_type':'TIR-NB-LRR','plant':'Phaseolus vulgaris'},
    'Fom-1':   {'virus':'PRSV','effector':'-','nlr_type':'CNL-type','plant':'Cucumis melo'},
    'Rsv3':    {'virus':'Soybean mosaic virus (SMV)','effector':'CI, P3','nlr_type':'CC-NB-LRR','plant':'Glycine max'},
}

with open(os.path.join(outdir, 'all_genes_classified.json'), encoding='utf-8') as f:
    data = json.load(f)

# Update NLR genes
matched = 0
for g in data['nlr']:
    gid = g['gene_id']
    if gid in nlr_virus_map:
        info = nlr_virus_map[gid]
        g['virus'] = info['virus']
        g['effector'] = info['effector']
        g['nlr_type'] = info['nlr_type']
        if not g.get('species') or g['species'] == '?':
            g['species'] = info['plant']
        g['domain_type'] = 'TNL' if 'TIR' in info['nlr_type'] else 'CNL'
        matched += 1

print(f'Updated {matched} NLR genes with virus/effector data')

# Also add missing ones as new entries
existing_ids = set(g['gene_id'] for g in data['nlr'])
added = 0
for gid, info in nlr_virus_map.items():
    if gid not in existing_ids:
        data['nlr'].append({
            'gene_id': gid, 'symbol': gid, 'full_name': f'{info["nlr_type"]} resistance gene {gid}',
            'species': info['plant'], 'domain_type': 'TNL' if 'TIR' in info['nlr_type'] else 'CNL',
            'validated': 'V', 'virus': info['virus'], 'effector': info['effector'],
            'uniprot': ''
        })
        added += 1

print(f'Added {added} new NLR entries')
print(f'Total NLR: {len(data["nlr"])}')

# Save
with open(os.path.join(outdir, 'all_genes_classified.json'), 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)

write_gene_data_js(outdir, {
    (key.upper() if key != 'mirna' else 'MIRNA') + '_DATA': json.dumps(data[key], ensure_ascii=False)
    for key in ['nlr', 'srna', 'ups', 'mirna'] if key in data
})

print('Done')
