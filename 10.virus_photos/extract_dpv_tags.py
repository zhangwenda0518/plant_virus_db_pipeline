import json, re, pathlib

DPV_JSON = pathlib.Path(__file__).resolve().parent.parent / "docs/data/dpv_gallery.json"

# Load DPV data
with open(DPV_JSON, 'r', encoding='utf-8') as f:
    dpv = json.load(f)

HOST_MAP = {
    'tomato':'Solanum lycopersicum','tobacco':'Nicotiana tabacum','potato':'Solanum tuberosum',
    'cucumber':'Cucumis sativus','pepper':'Capsicum annuum','bean':'Phaseolus vulgaris',
    'soybean':'Glycine max','pea':'Pisum sativum','cowpea':'Vigna unguiculata',
    'wheat':'Triticum aestivum','barley':'Hordeum vulgare','maize':'Zea mays',
    'corn':'Zea mays','rice':'Oryza sativa','sugarcane':'Saccharum officinarum',
    'cotton':'Gossypium hirsutum','grape':'Vitis vinifera','apple':'Malus domestica',
    'peach':'Prunus persica','plum':'Prunus domestica','cherry':'Prunus avium',
    'citrus':'Citrus spp.','banana':'Musa spp.','papaya':'Carica papaya',
    'onion':'Allium cepa','garlic':'Allium sativum','carrot':'Daucus carota',
    'lettuce':'Lactuca sativa','spinach':'Spinacia oleracea','cabbage':'Brassica oleracea',
    'cauliflower':'Brassica oleracea','broccoli':'Brassica oleracea','sunflower':'Helianthus annuus',
    'peanut':'Arachis hypogaea','sorghum':'Sorghum bicolor','oat':'Avena sativa',
    'rye':'Secale cereale','sweet potato':'Ipomoea batatas','cassava':'Manihot esculenta',
    'yam':'Dioscorea spp.','cocoa':'Theobroma cacao','coffee':'Coffea arabica',
    'coconut':'Cocos nucifera','oil palm':'Elaeis guineensis','rubber':'Hevea brasiliensis',
    'strawberry':'Fragaria x ananassa','raspberry':'Rubus idaeus','blueberry':'Vaccinium corymbosum',
    'watermelon':'Citrullus lanatus','melon':'Cucumis melo','pumpkin':'Cucurbita moschata',
    'squash':'Cucurbita pepo','zucchini':'Cucurbita pepo','celery':'Apium graveolens',
    'parsley':'Petroselinum crispum','basil':'Ocimum basilicum','mint':'Mentha spp.',
    'rose':'Rosa spp.','chrysanthemum':'Chrysanthemum morifolium','orchid':'Orchidaceae',
    'petunia':'Petunia x hybrida','dahlia':'Dahlia pinnata',
    'sugar beet':'Beta vulgaris','beet':'Beta vulgaris','clover':'Trifolium spp.',
    'alfalfa':'Medicago sativa','lucerne':'Medicago sativa','olive':'Olea europaea',
    'almond':'Prunus dulcis','apricot':'Prunus armeniaca','pear':'Pyrus communis',
    'quince':'Cydonia oblonga','fig':'Ficus carica','date':'Phoenix dactylifera',
    'mango':'Mangifera indica','avocado':'Persea americana','pineapple':'Ananas comosus',
    'guava':'Psidium guajava','pomegranate':'Punica granatum','kiwi':'Actinidia deliciosa',
    'hop':'Humulus lupulus','hemp':'Cannabis sativa','flax':'Linum usitatissimum',
    'millet':'Panicum miliaceum','bamboo':'Bambusoideae','saffron':'Crocus sativus',
    'lily':'Lilium spp.','tulip':'Tulipa spp.','daffodil':'Narcissus spp.',
    'carnation':'Dianthus caryophyllus','geranium':'Pelargonium spp.','poinsettia':'Euphorbia pulcherrima',
    'gladiolus':'Gladiolus spp.','iris':'Iris spp.','narcissus':'Narcissus spp.',
}

SYMP_KW = ['mosaic','mottle','necrosis','chlorosis','yellowing','yellow',
           'stunting','stunt','ringspot','spot','streak','wilt',
           'leaf curl','curling','blister','distortion','crinkle',
           'malformation','vein banding','vein clearing','etch','pitting',
           'lesion','enation','gall','tumor','dwarf','rosette',
           'line pattern','ring pattern','blotch','scorch','decline',
           'dieback','canker','browning','rust','powdery mildew']

# Standardize symptom names
SYMP_STD = {
    'mosaic':'mosaic','mottle':'mottle','necrosis':'necrosis','chlorosis':'chlorosis',
    'yellowing':'yellowing','yellow':'yellowing','stunting':'stunting','stunt':'stunting',
    'ringspot':'ringspot','spot':'spot','streak':'streak','wilt':'wilt',
    'leaf curl':'leaf curl','curling':'leaf curl','blister':'blister',
    'distortion':'distortion','crinkle':'crinkle','malformation':'malformation',
    'vein banding':'vein banding','vein clearing':'vein clearing','etch':'etch',
    'pitting':'pitting','lesion':'lesion','enation':'enation','gall':'gall',
    'tumor':'tumor','dwarf':'dwarf','rosette':'rosette','line pattern':'line pattern',
    'ring pattern':'ring pattern','blotch':'blotch','scorch':'scorch','decline':'decline',
    'dieback':'dieback','canker':'canker','browning':'browning','rust':'rust',
    'powdery mildew':'powdery mildew',
}

PART_KW = {
    'leaf':'leaf','leaves':'leaf','fruit':'fruit','fruits':'fruit',
    'stem':'stem','stems':'stem','root':'root','roots':'root',
    'flower':'flower','flowers':'flower','seed':'seed','seeds':'seed',
    'pod':'pod','pods':'pod','shoot':'shoot','shoots':'shoot',
    'tuber':'tuber','tubers':'tuber','bulb':'bulb','bulbs':'bulb',
    'bark':'bark','branch':'branch','branches':'branch',
    'petal':'petal','petals':'petal','berry':'fruit','berries':'fruit',
    'grain':'grain','grains':'grain','head':'head','cob':'cob',
    'ear':'ear','panicle':'panicle','inflorescence':'inflorescence',
    'whole plant':'whole plant','seedling':'seedling','seedlings':'seedling',
    'cotyledon':'cotyledon','cotyledons':'cotyledon','trunk':'trunk',
    'crown':'crown','tendril':'tendril','tendrils':'tendril',
}

def extract_tags(caption):
    cap_lower = caption.lower()

    # Extract Latin names from *italic* markers (Genus species pattern)
    italic_names = re.findall(r'\*([^*]+)\*', caption)
    hosts = []
    for name in italic_names:
        name = name.strip()
        if re.match(r'^[A-Z][a-z]+ [a-z]+', name):
            hosts.append(name)

    # Also check for common names
    for common, latin in HOST_MAP.items():
        if common.lower() in cap_lower:
            if latin not in hosts:
                hosts.append(latin)

    # Extract symptoms
    symptoms = []
    for kw in SYMP_KW:
        if kw in cap_lower:
            std = SYMP_STD[kw]
            if std not in symptoms:
                symptoms.append(std)

    # Extract parts
    parts = []
    for kw, std in PART_KW.items():
        if kw in cap_lower:
            if std not in parts:
                parts.append(std)

    return hosts, symptoms, parts

def build_hosts_latin(hosts):
    result = []
    for h in hosts:
        common = ''
        for c, l in HOST_MAP.items():
            if l == h:
                common = c
                break
        result.append({'latin': h, 'cn': common or h, 'common': common})
    return result

# Process
for d in dpv:
    hosts, symptoms, parts = extract_tags(d.get('caption', ''))
    d['hosts'] = hosts
    d['hosts_latin'] = build_hosts_latin(hosts)
    d['symptoms'] = symptoms
    d['parts'] = parts

# Save
with open(DPV_JSON, 'w', encoding='utf-8') as f:
    json.dump(dpv, f, ensure_ascii=False, indent=2)

has_hosts = sum(1 for x in dpv if x.get('hosts') and len(x['hosts']) > 0)
has_symp = sum(1 for x in dpv if x.get('symptoms') and len(x['symptoms']) > 0)
has_parts = sum(1 for x in dpv if x.get('parts') and len(x['parts']) > 0)
print(f'DPV: {len(dpv)} entries')
print(f'Has hosts: {has_hosts}, Has symptoms: {has_symp}, Has parts: {has_parts}')

# Sample
for d in dpv[:5]:
    print(f'\n--- {d["code"]} ---')
    print(f'Caption: {d["caption"][:120]}')
    print(f'Hosts: {d["hosts"]}')
    print(f'Symptoms: {d["symptoms"]}')
    print(f'Parts: {d["parts"]}')
