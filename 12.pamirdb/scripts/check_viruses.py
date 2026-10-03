import json, pathlib
v = json.load(open(pathlib.Path(__file__).resolve().parent.parent / "data/viruses.json"))
for vid, info in v.items():
    print(f"{vid:25s} {info['family']:20s} {info['genome_length']:8d} bp  {info['name'][:60]}")
