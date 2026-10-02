# -*- coding: utf-8 -*-
"""给两个 step5 web server 打跨库 AI 补丁（媒介库/照片库/深链/KB 全上下文/链接化）。"""
from pathlib import Path

ROOT = Path(r"D:\桌面\C-host_classify\plant_virus_db_pipeline")

MODULE_BLOCK = '''

# ── 跨库取数：媒介-宿主库（8.plant-insect）+ 症状照片库（docs/data）──
def _pipeline_candidates(rel):
    return (Path("/opt/plant_virus_db/plant_virus_db_pipeline") / rel,
            Path(__file__).resolve().parent.parent / rel)

_VECTOR_INDEX = None
_PHOTO_INDEX = None
_SYMPTOM_INDEX = None


def _bridge_canonical(name):
    """俗名/别名 → ICTV 规范名（走别名词典，取首个命中）。"""
    lst = _build_species_aliases().get((name or '').strip().lower())
    return lst[0] if lst else None


def _canon_of(name):
    """词典直接命中失败时退回 n-gram 扫描（如 'Alfamovirus AMV' → AMV → Alfalfa mosaic virus）。"""
    canon = _bridge_canonical(name)
    if canon:
        return canon
    ext = _extract_species_from_message(name or '', 1)
    return ext[0][0] if ext else None


def _build_vector_index():
    global _VECTOR_INDEX
    if _VECTOR_INDEX is None:
        _VECTOR_INDEX = {}
        for p in _pipeline_candidates("8.plant-insect/virus_vector_merged.json"):
            if not p.exists():
                continue
            try:
                d = json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                continue
            for v in d.get('viruses') or []:
                names = [v.get('ictv_name') or '', v.get('canonical_name') or '']
                names += list(v.get('matched_names') or [])
                for nm in names:
                    canon = _bridge_canonical(nm)
                    if canon:
                        _VECTOR_INDEX.setdefault(canon, v)
            break
    return _VECTOR_INDEX


def _build_media_indexes():
    global _PHOTO_INDEX, _SYMPTOM_INDEX
    if _PHOTO_INDEX is not None:
        return
    _PHOTO_INDEX, _SYMPTOM_INDEX = {}, {}
    for p in _pipeline_candidates("docs/data/unified_gallery.json"):
        if p.exists():
            try:
                items = json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                items = []
            for it in items or []:
                canon = _canon_of((it.get('virus_ictv') or '') or (it.get('virus') or ''))
                if not canon:
                    continue
                lst = _PHOTO_INDEX.setdefault(canon, [])
                if len(lst) < 3:
                    lst.append({'thumb': (it.get('thumb') or '').strip(),
                                'full': (it.get('full') or '').strip(),
                                'caption': (it.get('capt') or it.get('caption') or '').strip()[:120]})
            break
    for p in _pipeline_candidates("docs/data/symptom_table.json"):
        if p.exists():
            try:
                items = json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                items = []
            for it in items or []:
                canon = _canon_of(it.get('virus') or '')
                s = (it.get('symptoms_std') or it.get('symptoms') or '').strip()
                if not canon or not s:
                    continue
                host = (it.get('host_latin') or '').strip()
                entry = s + ((' (host: ' + host + ')') if host else '')
                lst = _SYMPTOM_INDEX.setdefault(canon, [])
                if entry not in lst and len(lst) < 4:
                    lst.append(entry)
            break


def _cross_db_info(canons, base, zh=False):
    """媒介-宿主 + 症状照片 + 站内深链，一次取齐供 AI 回填。"""
    import re as _re
    from urllib.parse import quote as _q
    vidx = _build_vector_index()
    _build_media_indexes()
    lines = []
    for c in canons[:3]:
        v = vidx.get(c)
        if v:
            vectors, modes, hosts, dois = [], [], [], []
            for r in (v.get('relationships') or [])[:10]:
                for key, bag, cap in (('vector', vectors, 6), ('host', hosts, 5)):
                    val = (r.get(key) or '').strip()
                    if val and val not in bag and len(bag) < cap:
                        bag.append(val)
                m = (r.get('transmission_mode') or r.get('transmission_category') or '').strip()
                if m and m not in modes and len(modes) < 3:
                    modes.append(m)
                for dk in ('doi_insect', 'doi_transmission'):
                    for one in _re.split(r'[;；,，\\s]+', (r.get(dk) or '').strip()):
                        if one.startswith('http') and one not in dois and len(dois) < 2:
                            dois.append(one)
            seg = f"- {'媒介-宿主库' if zh else 'Vector-host DB'} | {c}"
            ictv = (v.get('ictv_name') or '').strip()
            if ictv and ictv != c:
                seg += f" ({ictv})"
            lines.append(seg + ":")
            if vectors:
                lines.append(f"  {'传播介体' if zh else 'vectors'}: {'; '.join(vectors)}")
            if modes:
                lines.append(f"  {'传播方式' if zh else 'transmission'}: {'; '.join(modes)}")
            if hosts:
                lines.append(f"  {'宿主(部分)' if zh else 'hosts (examples)'}: {'; '.join(hosts)}")
            if dois:
                lines.append(f"  {'证据' if zh else 'evidence'}: {'; '.join(dois)}")
        photos = _PHOTO_INDEX.get(c) or []
        sympt = _SYMPTOM_INDEX.get(c) or []
        if photos or sympt:
            lines.append(f"- {'症状照片库' if zh else 'Symptom records'} | {c}:")
            for ph in photos[:2]:
                if ph['thumb']:
                    lines.append(f"  {'照片' if zh else 'photo'}: {ph['thumb']}"
                                 + (f" ({ph['caption']})" if ph['caption'] else ''))
            if sympt:
                lines.append(f"  {'典型症状' if zh else 'typical symptoms'}: {' | '.join(sympt[:3])}")
    if canons:
        q = _q(canons[0])
        links = [('引物检索', 'Primers search', f'{base}/primers/search?q={q}'),
                 ('物种页', 'Species page', f'{base}/species/{q}'),
                 ('时空探索器', 'Explorer profile', f'{base}/explorer/?profile={q}'),
                 ('媒介库', 'Vector-host DB', f'{base}/vector/'),
                 ('症状照片', 'Symptom photos', f'{base}/photos/'),
                 ('知识库', 'Knowledge base', f'{base}/knowledge/')]
        if zh:
            lines.append("- 站内深链（回答末尾请附“相关页面直达：”一节，逐字列出以下网址）:")
            lines += [f"  {a}: {u}" for a, _, u in links]
        else:
            lines.append("- Deep links (end your reply with a 'Relevant pages:' section quoting these URLs verbatim):")
            lines += [f"  {b}: {u}" for _, b, u in links]
    if not lines:
        return ""
    head = ("\\n\\n【跨库记录——请与引物/知识数据一并引用】:\\n" if zh
            else "\\n\\n[Cross-database records — cite these alongside the primers/knowledge data]:\\n")
    return head + "\\n".join(lines) + "\\n"

'''

A_CANON_OLD = """        extra_info = ""
        try:
            for canon, matched in _extract_species_from_message(user_msg):
"""
A_CANON_NEW = """        extra_info = ""
        canon_list = []
        try:
            for canon, matched in _extract_species_from_message(user_msg):
                canon_list.append(canon)
"""

A_SPECIES_EXC = """        except Exception as e:
            app.logger.warning("[api/chat] species lookup failed: %s", e)
"""

KB_OLD_EN = """        kb_info = ""
        if context in ('explorer', 'reference_db'):
            try:
                rr = requests.get(KB_SEARCH_URL, params={"q": user_msg, "limit": 3}, timeout=8)
                if rr.status_code == 200:
                    items = (rr.json() or {}).get("results") or []
                    if items:
                        kb_info = "\\n\\n[Knowledge base fragments — ground virus-biology answers in these and cite the [SOURCE]]:\\n"
                        for k, it in enumerate(items, 1):
                            kb_info += f"[{k}] ({it.get('source', '')}) {it.get('title', '')}: {(it.get('text') or '')[:600]}\\n"
            except Exception as e:
                app.logger.warning("[api/chat] KB retrieval failed: %s", e)
"""
KB_NEW_EN = """        kb_info = ""
        try:
            rr = requests.get(KB_SEARCH_URL, params={"q": user_msg, "limit": 3}, timeout=8)
            if rr.status_code == 200:
                items = (rr.json() or {}).get("results") or []
                if items:
                    kb_info = "\\n\\n[Knowledge base fragments — ground virus-biology answers in these and cite the [SOURCE]]:\\n"
                    for k, it in enumerate(items, 1):
                        kb_info += f"[{k}] ({it.get('source', '')}) {it.get('title', '')}: {(it.get('text') or '')[:600]}\\n"
        except Exception as e:
            app.logger.warning("[api/chat] KB retrieval failed: %s", e)
"""

KB_OLD_ZH = """        kb_info = ""
        if context in ('explorer', 'reference_db'):
            try:
                rr = requests.get(KB_SEARCH_URL, params={"q": user_msg, "limit": 3}, timeout=8)
                if rr.status_code == 200:
                    items = (rr.json() or {}).get("results") or []
                    if items:
                        kb_info = "\\n\\n[知识库检索片段——回答病毒学内容时请以这些片段为准并标注 [来源]]:\\n"
                        for k, it in enumerate(items, 1):
                            kb_info += f"[{k}] ({it.get('source', '')}) {it.get('title', '')}: {(it.get('text') or '')[:600]}\\n"
            except Exception as e:
                app.logger.warning("[api/chat] KB retrieval failed: %s", e)
"""
KB_NEW_ZH = """        kb_info = ""
        try:
            rr = requests.get(KB_SEARCH_URL, params={"q": user_msg, "limit": 3}, timeout=8)
            if rr.status_code == 200:
                items = (rr.json() or {}).get("results") or []
                if items:
                    kb_info = "\\n\\n[知识库检索片段——回答病毒学内容时请以这些片段为准并标注 [来源]]:\\n"
                    for k, it in enumerate(items, 1):
                        kb_info += f"[{k}] ({it.get('source', '')}) {it.get('title', '')}: {(it.get('text') or '')[:600]}\\n"
        except Exception as e:
            app.logger.warning("[api/chat] KB retrieval failed: %s", e)
"""

WIDGET_OLD = """        div.className = 'chat-msg ' + role;
        div.textContent = text;
"""
WIDGET_NEW = """        div.className = 'chat-msg ' + role;
        var safe = String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        safe = safe.replace(/(https?:\\/\\/[^\\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
        div.innerHTML = safe.replace(/\\n/g, '<br>');
"""

# 每个文件: (xlib 代码, prompt 补丁列表 [(anchor, addition)])
FILES = {
    "4.virus_primer/step5_web_server.py": {
        "zh": False,
        "kb_old": KB_OLD_EN, "kb_new": KB_NEW_EN,
        "prompts": [
            ('- Species are stored under ICTV canonical binomials (e.g. "Tomato yellow leaf curl virus" → "Begomovirus coheni"). When species records are attached after the user\'s message, answer from them directly and mention the canonical name used.',
             '\n- Vector-host relationships, symptom photos and deep links are also attached when a species is resolved: weave relevant ones into the answer and end with a "Relevant pages:" section quoting the provided URLs verbatim.'),
            ('- If knowledge base fragments are attached below, ground biology answers in them and cite the sources; if they are insufficient, say so instead of fabricating.',
             '\n- Cross-database records (vector-host, symptom photos) and deep links may also be attached; use them the same way and end with the "Relevant pages:" section.'),
            ('- If knowledge base fragments are attached below, ground biology answers in them and cite the sources; otherwise say when you are not certain.',
             '\n- Cross-database records (vector-host, symptom photos) and deep links may also be attached; use them the same way and end with the "Relevant pages:" section.'),
        ],
    },
    "4.virus_primer/step5_web_server_PROD.py": {
        "zh": True,
        "kb_old": KB_OLD_ZH, "kb_new": KB_NEW_ZH,
        "prompts": [
            ('- 库内物种按 ICTV 规范双名存储（如 "Tomato yellow leaf curl virus" → "Begomovirus coheni"）。用户消息后附有解析出的物种记录时，直接基于这些记录回答，并说明所用的规范名。',
             '\n- 用户消息后还可能附有跨库记录（媒介-宿主关系、症状照片、站内深链）：把相关内容融入回答，并在末尾附“相关页面直达：”一节，逐字列出给出的网址。'),
            ('- 若下方附有知识库检索片段，病毒学内容请以片段为准并标注来源；片段不足以回答时如实说明，不要编造。',
             '\n- 附有跨库记录（媒介-宿主、症状照片、站内深链）时同样引用使用，并在末尾附“相关页面直达：”一节。'),
            ('- 若下方附有知识库检索片段，病毒学内容请以片段为准并标注来源；没有片段时对不确定的内容如实说明。',
             '\n- 附有跨库记录（媒介-宿主、症状照片、站内深链）时同样引用使用，并在末尾附“相关页面直达：”一节。'),
        ],
    },
}

for rel, cfg in FILES.items():
    p = ROOT / rel
    t = p.read_text(encoding='utf-8')

    def rep(old, new, label):
        global t
        n = t.count(old)
        assert n == 1, f"{rel}: {label} anchor count={n}"
        t = t.replace(old, new)

    # 1) 模块级跨库层
    kb_line = "KB_SEARCH_URL = SERVER_AI_CONFIG.get('KB_SEARCH_URL', 'http://127.0.0.1:5002/search')\n"
    rep(kb_line, kb_line + MODULE_BLOCK, "KB_SEARCH_URL")

    # 2) canon_list
    rep(A_CANON_OLD, A_CANON_NEW, "canon_list")

    # 3) xlib 块
    zh_flag = "True" if cfg["zh"] else "False"
    xlib = A_SPECIES_EXC + f"""
        # 跨库取数：媒介-宿主 + 症状照片 + 站内深链（解析到物种时附加）
        xlib_info = ""
        if canon_list:
            try:
                xlib_info = _cross_db_info(canon_list, request.host_url.rstrip('/'), zh={zh_flag})
            except Exception as e:
                app.logger.warning("[api/chat] cross-db lookup failed: %s", e)
"""
    rep(A_SPECIES_EXC, xlib, "species-except+xlib")

    # 4) KB 去掉上下文门控
    rep(cfg["kb_old"], cfg["kb_new"], "kb-gate")

    # 5) 消息拼接
    rep('user_msg + extra_info + kb_info', 'user_msg + extra_info + xlib_info + kb_info', "append")

    # 6) 提示词
    for anchor, addition in cfg["prompts"]:
        rep(anchor, anchor + addition, "prompt")

    # 7) 前端链接化
    rep(WIDGET_OLD, WIDGET_NEW, "widget-linkify")

    p.write_text(t, encoding='utf-8', newline='\n')
    print("patched", rel)
print("ALL OK")
