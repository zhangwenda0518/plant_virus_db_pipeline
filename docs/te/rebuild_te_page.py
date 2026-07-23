#!/usr/bin/env python3
"""Rebuild TE page from broken version by extracting and reordering sections."""
import os

p = '/opt/plant_virus_db/plant_virus_db_pipeline/docs/te/index.html'
with open(p, encoding='utf-8') as f:
    html = f.read()

# Strategy: Find the unique markers that define section boundaries
# Each section starts at a marker and ends before the next marker

MARKERS = {
    'head_nav': (html.find('<nav'), html.find('<div class="hero"')),
    'hero': (html.find('<div class="hero"'), html.find('<!-- KPI Row -->')),
}

# Find all occurrences of each marker
marker_names = [
    '<!-- KPI Row -->',
    '<!-- Introduction -->',
    '<!-- Charts Row 1 -->',
    '<!-- Charts Row 2 -->',
    'id="seqTable"',
    '<!-- Download Section -->',
    '<!-- Pipeline Info -->',
    '<div class="footer"',
    '<script>',
]

positions = {}
for name in marker_names:
    # Find the LAST occurrence (the one in the correct position)
    pos = html.rfind(name)
    # But for seqTable, find the div that contains it
    if name == 'id="seqTable"':
        # Find opening <div class="card" before this
        div_pos = html.rfind('<div class="card" id="seqTable"', 0, pos + 100)
        positions['seq_browser'] = div_pos if div_pos >= 0 else pos
    else:
        positions[name] = pos

# Sort by position
ordered = sorted([(v, k) for k, v in positions.items() if v >= 0])
print("Section boundaries:")
for pos, name in ordered:
    print(f"  {name} @ {pos}")

# Extract sections using these positions
sections = {}
for i, (start, name) in enumerate(ordered):
    if i + 1 < len(ordered):
        end = ordered[i + 1][0]
    else:
        end = len(html)
    sections[name] = html[start:end]

# Get everything BEFORE the first section (head, nav)
first_pos = ordered[0][0] if ordered else 0
prefix = html[:first_pos]

# Rebuild in desired order
desired = [
    '<!-- KPI Row -->',
    '<!-- Introduction -->',
    '<!-- Charts Row 1 -->',
    '<!-- Charts Row 2 -->',
    'seq_browser',
    '<!-- Download Section -->',
    '<!-- Pipeline Info -->',
]

# The end part (footer + script)
footer_key = '<div class="footer"'
script_key = '<script>'

new_html = prefix
for name in desired:
    if name in sections:
        new_html += sections[name]

# Add footer + script
if footer_key in sections:
    new_html += sections[footer_key]
if script_key in sections:
    new_html += sections[script_key]

# Verify no duplicates
for m in marker_names:
    if m == 'id="seqTable"':
        continue
    count = new_html.count(m)
    if count > 1:
        print(f"  WARNING: '{m}' appears {count} times")

with open(p, 'w', encoding='utf-8') as f:
    f.write(new_html)

print("\nNew structure:")
for name in desired:
    pos = new_html.find(name if name != 'seq_browser' else 'id="seqTable"')
    if pos >= 0:
        ln = new_html[:pos].count('\n') + 1
        label = name if name != 'seq_browser' else 'Sequence Browser'
        print(f"  {label} @ line {ln}")
