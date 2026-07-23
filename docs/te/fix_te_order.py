#!/usr/bin/env python
"""Move Sequence Browser table to right after KPIs in TE page."""
lines = open("te_index_full.html", encoding="utf-8").readlines()
table_block = lines[187:224]  # Card div + trailing blank
del lines[187:224]
lines[105:105] = table_block
open("te_index_full.html", "w", encoding="utf-8").writelines(lines)
print("Moved table from line 188 to line 106")
