#!/usr/bin/env python3
"""
1KP Transcriptome Virus Detection Dashboard
============================================
独立 Dash 应用，挂载于 /onekp/，展示 1,341 个植物转录组样本的病毒组检测结果。

访问: http://localhost:8051/onekp/
"""

import os, sys, pickle
import pandas as pd
import numpy as np
import dash
from dash import dcc, html, Input, Output, callback, dash_table
import dash_mantine_components as dmc
import plotly.express as px
import plotly.graph_objects as go

# ── 路径设置 ──────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, ".cache")
CACHE_FILE = os.path.join(CACHE_DIR, "onekp_data.pkl")
ENRICHED_FILE = os.path.join(CACHE_DIR, "onekp_enriched.pkl")
RESULTS_DIR = BASE_DIR  # data TSVs/CSVs are alongside app
ENC = "utf-16-le"

# ── 加载数据（优先 enriched pickle → 基础 pickle → TSV 直接加载）──
def _load_data():
    """Try enriched pickle first; fall back to basic pickle; then raw TSV."""

    # Try enriched pickle
    if os.path.exists(ENRICHED_FILE):
        try:
            with open(ENRICHED_FILE, "rb") as f:
                cache = pickle.load(f)
            print("Loaded from enriched pickle cache")
            summary = {
                "total_samples_in_run": 1341,
                "infected_samples_raw": int(cache["all_data"]["Sample"].nunique()),
                "infected_samples_hc": int(cache["hc"]["Sample"].nunique()),
                "virus_species_raw": int(cache["all_data"]["Adjusted_Species"].nunique()),
                "virus_species_hc": int(cache["hc"]["Adjusted_Species"].nunique()),
                "records_raw": int(len(cache["all_data"])),
                "records_hc": int(len(cache["hc"])),
                "records_discarded": int(len(cache["discarded"])),
                "pipeline_runtime": "1h 56m 34s",
                "peak_memory_mb": 2069.7,
            }
            return cache["all_data"], cache["hc"], cache["discarded"], summary, cache.get("host_summary", {})
        except Exception as e:
            print(f"Enriched pickle failed ({e}), trying basic...")

    # Try basic pickle
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "rb") as f:
                cache = pickle.load(f)
            print("Loaded from basic pickle cache")
            return cache["all_data"], cache["hc"], cache["discarded"], cache["summary"], {}
        except Exception as e:
            print(f"Basic pickle failed ({e}), loading from TSV...")

    # Fall back to TSV
    raw = pd.read_csv(os.path.join(RESULTS_DIR, "all_viruses.best.summary.tsv"),
                      sep="\t", encoding=ENC, low_memory=False)
    hc = pd.read_csv(os.path.join(RESULTS_DIR, "high_conf.summary.tsv"),
                     sep="\t", encoding=ENC, low_memory=False)
    disc = pd.read_csv(os.path.join(RESULTS_DIR, "high_conf.summary.discarded.tsv"),
                       sep="\t", encoding=ENC, low_memory=False)
    raw["Confidence"] = "Low"
    hc["Confidence"] = "High"
    disc["Confidence"] = "Low"

    # Try to enrich with host metadata
    host_summary = {}
    try:
        links_path = os.path.join(BASE_DIR, "onekp_download_links.csv")
        samples_path = os.path.join(BASE_DIR, "onekp_all_samples.csv")
        if os.path.exists(links_path) and os.path.exists(samples_path):
            import re
            links = pd.read_csv(links_path, encoding=ENC, low_memory=False)
            samples = pd.read_csv(samples_path, encoding=ENC, low_memory=False)
            def _extract_acc(url):
                if pd.isna(url): return None
                m = re.search(r'/([EDS]RR\d+)/', str(url))
                return m.group(1) if m else None
            links["accession"] = links["SRA Download"].apply(_extract_acc)
            acc_to_code = dict(zip(links["accession"], links["Sample Code"]))
            code_to_info = {}
            for _, r in samples.iterrows():
                code = str(r.get("Sample Code", "")).strip()
                if code:
                    code_to_info[code] = {
                        "host_species": str(r.get("Species", "")),
                        "host_clade": str(r.get("Clade", "")),
                        "host_order": str(r.get("Order", "")),
                        "host_family": str(r.get("Family", "")),
                        "host_tissue": str(r.get("Tissue", "")),
                    }
            acc_to_host = {}
            for acc, code in acc_to_code.items():
                if code in code_to_info:
                    acc_to_host[acc] = code_to_info[code]
            for df in [raw, hc, disc]:
                df["host_species"] = df["Sample"].map(lambda x: acc_to_host.get(x, {}).get("host_species", ""))
                df["host_clade"] = df["Sample"].map(lambda x: acc_to_host.get(x, {}).get("host_clade", ""))
                df["host_order"] = df["Sample"].map(lambda x: acc_to_host.get(x, {}).get("host_order", ""))
                df["host_family"] = df["Sample"].map(lambda x: acc_to_host.get(x, {}).get("host_family", ""))
                df["host_tissue"] = df["Sample"].map(lambda x: acc_to_host.get(x, {}).get("host_tissue", ""))
            matched = raw[raw["host_species"] != ""]
            host_summary = {
                "total_host_species": int(matched["host_species"].nunique()),
                "total_host_families": int(matched["host_family"].nunique()),
                "total_host_orders": int(matched["host_order"].nunique()),
                "total_host_clades": int(matched["host_clade"].nunique()),
            }
            print(f"Enriched with host metadata: {len(acc_to_host)} accessions mapped")
    except Exception as e:
        print(f"Host enrichment skipped: {e}")
    summary = {
        "total_samples_in_run": 1341,
        "infected_samples_raw": int(raw["Sample"].nunique()),
        "infected_samples_hc": int(hc["Sample"].nunique()),
        "virus_species_raw": int(raw["Adjusted_Species"].nunique()),
        "virus_species_hc": int(hc["Adjusted_Species"].nunique()),
        "records_raw": int(len(raw)),
        "records_hc": int(len(hc)),
        "records_discarded": int(len(disc)),
        "pipeline_runtime": "1h 56m 34s",
        "peak_memory_mb": 2069.7,
    }
    print(f"Loaded from TSV: {len(raw)} records")
    return raw, hc, disc, summary, host_summary

ALL_DATA, HC_DATA, DISCARDED, SUMMARY, HOST_SUMMARY = _load_data()
HAS_HOST = bool(HOST_SUMMARY)

# ── 预计算 ────────────────────────────────────────────
VIRUS_LIST = sorted(ALL_DATA["Adjusted_Species"].dropna().unique().tolist())
VIRUS_OPTIONS = [{"value": v, "label": v} for v in VIRUS_LIST]

MOL_TYPES = sorted(ALL_DATA["Molecule_type"].dropna().unique().tolist())
MOL_OPTIONS = [{"value": m, "label": m} for m in MOL_TYPES]

# ── 颜色方案 ───────────────────────────────────────────
COLORS = ["#2e86c1", "#e74c3c", "#27ae60", "#f39c12", "#8e44ad",
          "#1abc9c", "#e67e22", "#2980b9", "#c0392b", "#16a085"]
NAV_BG = "#1a5276"

# ── Dash 应用 ──────────────────────────────────────────
app = dash.Dash(
    __name__,
    url_base_pathname="/onekp/",
    external_stylesheets=[],
    title="1KP Virome — PlantVirusDB",
    update_title=None,
)
# 全站统一 AI 悬浮窗（/api/chat 由 nginx 路由到引物服务后端）
app.index_string = '''<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        <script src="/lib/site-nav.js?v=2"></script>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        <script src="/lib/ai-assistant.js?v=2" data-context="onekp" defer></script>
    </body>
</html>'''
server = app.server

# ═══════════════════════════════════════════════════════════
# 布局
# ═══════════════════════════════════════════════════════════

def make_kpi_card(label, value, color="#2e86c1", subtitle=""):
    return dmc.Card(
        withBorder=True, shadow="sm", p="md", radius="md",
        style={"textAlign": "center", "minWidth": "140px"},
        children=[
            dmc.Text(str(value), size="xl", fw=700, c=color),
            dmc.Text(label, size="xs", c="dimmed"),
            dmc.Text(subtitle, size="xs", c="dimmed", mt=2) if subtitle else None,
        ],
    )

app.layout = dmc.MantineProvider(
    theme={"fontFamily": "Inter, -apple-system, sans-serif", "primaryColor": "blue"},
    children=[
        dcc.Store(id="confidence-mode", data="high"),  # high / all

        # ── 导航栏 ──
        dmc.AppShell(
            padding="md",
            children=[
                html.Div(
                    dmc.Group(
                        justify="flex-end", gap="xs",
                        children=[
                            dmc.Badge("1,341 samples", color="gray", variant="filled"),
                            dmc.Badge(f"{SUMMARY['virus_species_raw']} virus species", color="blue", variant="filled"),
                            dmc.Badge("1KP Project", color="green", variant="light"),
                        ]
                    ),
                    style={"padding": "2px 6px 8px 0"},
                ),
                dmc.AppShellMain(children=[

                    # ── Hero 区 ──
                    dmc.Paper(
                        withBorder=True, shadow="sm", p="lg", radius="md", mb="md",
                        style={"background": f"linear-gradient(135deg, {NAV_BG}, #2e86c1)"},
                        children=[
                            dmc.Title("1KP Transcriptome — Plant Virome Survey", order=2, c="white", mb="xs"),
                            dmc.Text(
                                "Virus detection across 1,341 plant transcriptomes from the One Thousand Plant Transcriptomes (1KP) Initiative. "
                                "Powered by MMPV-RNA pipeline: Salmon pseudoalignment → species-level virus identification → high-confidence filtering.",
                                size="sm", c="rgba(255,255,255,0.85)", style={"maxWidth": "900px", "lineHeight": 1.6},
                            ),
                            dmc.Space(h="sm"),
                            dmc.Text(
                                f"Pipeline runtime: {SUMMARY['pipeline_runtime']} · Peak memory: {SUMMARY['peak_memory_mb']:.0f} MB",
                                size="xs", c="rgba(255,255,255,0.6)",
                            ),
                        ],
                    ),

                    # ── KPI 行 ──
                    dmc.SimpleGrid(
                        cols={"base": 2, "sm": 3, "md": 6},
                        spacing="md",
                        mb="md",
                        children=[
                            make_kpi_card("Total Samples", f"{SUMMARY['total_samples_in_run']:,}", "#2e86c1"),
                            make_kpi_card("Infected Samples", str(SUMMARY['infected_samples_raw']), "#e74c3c"),
                            make_kpi_card("Virus Species", str(SUMMARY['virus_species_raw']), "#27ae60"),
                            make_kpi_card("High-Confidence", str(SUMMARY['records_hc']), "#f39c12"),
                            make_kpi_card("Filtered Out", str(SUMMARY['records_discarded']), "#8e44ad", "cov<50% or depth<5x"),
                            make_kpi_card("HC Samples", str(SUMMARY['infected_samples_hc']), "#1abc9c", "≥1 high-conf hit"),
                        ],
                    ),

                    # ── Host diversity KPI (if enriched data available) ──
                    dmc.SimpleGrid(
                        cols={"base": 2, "sm": 3, "md": 4},
                        spacing="md",
                        mb="md",
                        id="host-kpi-row",
                        children=[
                            make_kpi_card("Host Species", str(HOST_SUMMARY.get("total_host_species", "—")), "#e67e22"),
                            make_kpi_card("Host Families", str(HOST_SUMMARY.get("total_host_families", "—")), "#d35400"),
                            make_kpi_card("Host Orders", str(HOST_SUMMARY.get("total_host_orders", "—")), "#c0392b"),
                            make_kpi_card("Host Clades", str(HOST_SUMMARY.get("total_host_clades", "—")), "#8e44ad"),
                        ],
                    ) if HAS_HOST else None,

                    # ── 置信度切换 + 病毒筛选 ──
                    dmc.Paper(
                        withBorder=True, shadow="xs", p="sm", radius="md", mb="md",
                        children=dmc.Group(
                            gap="md", align="center",
                            children=[
                                dmc.Text("Confidence:", size="sm", fw=600),
                                dmc.SegmentedControl(
                                    id="conf-toggle",
                                    value="high",
                                    data=[
                                        {"value": "high", "label": f"High-Confidence ({SUMMARY['records_hc']})"},
                                        {"value": "all", "label": f"All Detections ({SUMMARY['records_raw']})"},
                                    ],
                                ),
                                dmc.Text("Virus filter:", size="sm", fw=600, ml="lg"),
                                dmc.MultiSelect(
                                    id="virus-select",
                                    data=VIRUS_OPTIONS,
                                    placeholder="All species",
                                    searchable=True,
                                    clearable=True,
                                    style={"minWidth": 320},
                                    nothingFoundMessage="No matching virus",
                                ),
                            ],
                        ),
                    ),

                    # ── 图表网格 ──
                    dmc.SimpleGrid(
                        cols={"base": 1, "md": 2},
                        spacing="md",
                        mb="md",
                        children=[

                            # 病毒发生率排名
                            dmc.Paper(
                                withBorder=True, shadow="xs", p="md", radius="md",
                                children=[
                                    dmc.Title("Virus Prevalence (Top 15)", order=5, mb="xs"),
                                    dmc.Text("Number of infected samples per virus species",
                                             size="xs", c="dimmed", mb="sm"),
                                    dcc.Loading(
                                        type="cube", color="#2e86c1",
                                        children=dcc.Graph(
                                            id="chart-prevalence",
                                            config={"displayModeBar": False},
                                            style={"height": "400px"},
                                        ),
                                    ),
                                ],
                            ),

                            # 覆盖度 vs 深度散点图
                            dmc.Paper(
                                withBorder=True, shadow="xs", p="md", radius="md",
                                children=[
                                    dmc.Title("Coverage vs Depth", order=5, mb="xs"),
                                    dmc.Text("Each point = one virus detection. High-conf threshold: cov≥50%, depth≥5x.",
                                             size="xs", c="dimmed", mb="sm"),
                                    dcc.Loading(
                                        type="cube", color="#2e86c1",
                                        children=dcc.Graph(
                                            id="chart-cov-depth",
                                            config={"displayModeBar": False},
                                            style={"height": "400px"},
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),

                    dmc.SimpleGrid(
                        cols={"base": 1, "md": 2},
                        spacing="md",
                        mb="md",
                        children=[

                            # 分子类型分布
                            dmc.Paper(
                                withBorder=True, shadow="xs", p="md", radius="md",
                                children=[
                                    dmc.Title("Molecule Type Distribution", order=5, mb="xs"),
                                    dcc.Loading(
                                        type="cube", color="#2e86c1",
                                        children=dcc.Graph(
                                            id="chart-moltype",
                                            config={"displayModeBar": False},
                                            style={"height": "360px"},
                                        ),
                                    ),
                                ],
                            ),

                            # 覆盖度直方图
                            dmc.Paper(
                                withBorder=True, shadow="xs", p="md", radius="md",
                                children=[
                                    dmc.Title("Genome Coverage Distribution", order=5, mb="xs"),
                                    dmc.Text("Red dashed line = 50% high-confidence threshold",
                                             size="xs", c="dimmed", mb="sm"),
                                    dcc.Loading(
                                        type="cube", color="#2e86c1",
                                        children=dcc.Graph(
                                            id="chart-coverage-hist",
                                            config={"displayModeBar": False},
                                            style={"height": "360px"},
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),

                    # ── 宿主-病毒关联 (enriched data only) ──
                    dmc.SimpleGrid(
                        cols={"base": 1, "md": 2},
                        spacing="md",
                        mb="md",
                        id="host-charts-row1",
                        children=[
                            dmc.Paper(
                                withBorder=True, shadow="xs", p="md", radius="md",
                                children=[
                                    dmc.Title("Virus × Host Family Heatmap", order=5, mb="xs"),
                                    dmc.Text("Top 12 viruses vs Top 10 host families. Color = infected samples.",
                                             size="xs", c="dimmed", mb="sm"),
                                    dcc.Loading(
                                        type="cube", color="#2e86c1",
                                        children=dcc.Graph(
                                            id="chart-virus-host-heatmap",
                                            config={"displayModeBar": False},
                                            style={"height": "420px"},
                                        ),
                                    ),
                                ],
                            ),
                            dmc.Paper(
                                withBorder=True, shadow="xs", p="md", radius="md",
                                children=[
                                    dmc.Title("Tissue Type Distribution (Infected Samples)", order=5, mb="xs"),
                                    dmc.Text("Plant tissue types from virus-positive transcriptomes",
                                             size="xs", c="dimmed", mb="sm"),
                                    dcc.Loading(
                                        type="cube", color="#2e86c1",
                                        children=dcc.Graph(
                                            id="chart-tissue-dist",
                                            config={"displayModeBar": False},
                                            style={"height": "420px"},
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ) if HAS_HOST else None,

                    dmc.SimpleGrid(
                        cols={"base": 1, "md": 2},
                        spacing="md",
                        mb="md",
                        id="host-charts-row2",
                        children=[
                            dmc.Paper(
                                withBorder=True, shadow="xs", p="md", radius="md",
                                children=[
                                    dmc.Title("Virus Species per Host Clade", order=5, mb="xs"),
                                    dmc.Text("Unique virus species detected in each plant evolutionary clade",
                                             size="xs", c="dimmed", mb="sm"),
                                    dcc.Loading(
                                        type="cube", color="#2e86c1",
                                        children=dcc.Graph(
                                            id="chart-clade-virus",
                                            config={"displayModeBar": False},
                                            style={"height": "380px"},
                                        ),
                                    ),
                                ],
                            ),
                            dmc.Paper(
                                withBorder=True, shadow="xs", p="md", radius="md",
                                children=[
                                    dmc.Title("Infected Samples per Host Family", order=5, mb="xs"),
                                    dmc.Text("Plant families ranked by number of virus-positive samples",
                                             size="xs", c="dimmed", mb="sm"),
                                    dcc.Loading(
                                        type="cube", color="#2e86c1",
                                        children=dcc.Graph(
                                            id="chart-host-family",
                                            config={"displayModeBar": False},
                                            style={"height": "380px"},
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ) if HAS_HOST else None,

                    # ── 数据表 ──
                    dmc.Paper(
                        withBorder=True, shadow="xs", p="md", radius="md", mb="md",
                        children=[
                            dmc.Title("Detection Records", order=5, mb="sm"),
                            dmc.Text(
                                "Sortable, filterable table. High-confidence records meet coverage ≥50%, depth ≥5x, reads ≥100.",
                                size="xs", c="dimmed", mb="sm",
                            ),
                            dcc.Loading(
                                type="cube", color="#2e86c1",
                                children=html.Div(
                                    id="records-table-container",
                                    style={"overflowX": "auto"},
                                ),
                            ),
                        ],
                    ),

                    # ── Footer ──
                    dmc.Center(
                        mt="lg",
                        children=dmc.Text(
                            "1KP Virome Dashboard · PlantVirusDB · MMPV-RNA Pipeline · Data generated 2026-07-25",
                            size="xs", c="dimmed",
                        ),
                    ),

                ]),  # end AppShellMain
            ],
        ),  # end AppShell
    ],
)

# ═══════════════════════════════════════════════════════════
# 回调
# ═══════════════════════════════════════════════════════════

def _get_filtered_df(conf_mode, virus_filter):
    """根据置信度模式和病毒筛选返回 DataFrame"""
    if conf_mode == "high":
        df = HC_DATA.copy()
    else:
        df = ALL_DATA.copy()

    if virus_filter:
        df = df[df["Adjusted_Species"].isin(virus_filter)]

    return df


@callback(
    Output("chart-prevalence", "figure"),
    Input("conf-toggle", "value"),
    Input("virus-select", "value"),
)
def update_prevalence(conf_mode, virus_filter):
    df = _get_filtered_df(conf_mode, virus_filter)
    vc = df.groupby("Adjusted_Species")["Sample"].nunique().sort_values(ascending=True).tail(15)
    if vc.empty:
        return go.Figure()
    fig = go.Figure(go.Bar(
        x=vc.values, y=vc.index, orientation="h",
        marker=dict(
            color=vc.values, colorscale="Blues", showscale=False,
            line=dict(color="rgba(0,0,0,0.1)", width=0.5),
        ),
        text=vc.values, textposition="outside",
        hovertemplate="%{y}<br>Samples: %{x}<extra></extra>",
    ))
    fig.update_layout(
        margin=dict(l=8, r=30, t=4, b=4),
        xaxis_title="Infected Samples",
        yaxis=dict(tickfont=dict(size=11)),
        plot_bgcolor="white",
        bargap=0.3,
    )
    return fig


@callback(
    Output("chart-cov-depth", "figure"),
    Input("conf-toggle", "value"),
    Input("virus-select", "value"),
)
def update_cov_depth(conf_mode, virus_filter):
    if conf_mode == "high":
        df = ALL_DATA.copy()
        df["Confidence"] = pd.Series(df.index.isin(HC_DATA.index)).map({True: "High", False: "Low"})
    else:
        df = ALL_DATA.copy()
        df["Confidence"] = "All"

    if virus_filter:
        df = df[df["Adjusted_Species"].isin(virus_filter)]

    if df.empty:
        return go.Figure()

    color_map = {"High": "#27ae60", "Low": "#e74c3c", "All": "#2e86c1"}

    fig = go.Figure()
    for conf, color in [("High", "#27ae60"), ("Low", "#e74c3c")]:
        sub = df[df["Confidence"] == conf]
        if not sub.empty:
            fig.add_trace(go.Scatter(
                x=sub["Rep_Coverage(%)"],
                y=sub["Rep_MeanDepth"].clip(upper=10000),
                mode="markers",
                name=conf,
                marker=dict(size=7, opacity=0.65, color=color,
                            line=dict(width=0.5, color="rgba(0,0,0,0.15)")),
                text=sub["Adjusted_Species"],
                hovertemplate="%{text}<br>Coverage: %{x:.1f}%<br>Depth: %{y:.1f}x<extra></extra>",
            ))

    # 阈值线
    fig.add_vline(x=50, line_dash="dash", line_color="gray", opacity=0.5,
                  annotation_text="cov=50%", annotation_position="top")
    fig.add_hline(y=5, line_dash="dash", line_color="gray", opacity=0.5,
                  annotation_text="depth=5x", annotation_position="right")

    fig.update_layout(
        margin=dict(l=8, r=8, t=4, b=4),
        xaxis_title="Genome Coverage (%)",
        yaxis_title="Mean Depth (×)",
        yaxis_type="log",
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


@callback(
    Output("chart-moltype", "figure"),
    Input("conf-toggle", "value"),
    Input("virus-select", "value"),
)
def update_moltype(conf_mode, virus_filter):
    df = _get_filtered_df(conf_mode, virus_filter)
    mc = df["Molecule_type"].value_counts()
    if mc.empty:
        return go.Figure()
    fig = go.Figure(go.Pie(
        labels=mc.index, values=mc.values,
        hole=0.45,
        marker=dict(colors=COLORS[:len(mc)]),
        textinfo="label+percent",
        textfont=dict(size=11),
    ))
    fig.update_layout(
        margin=dict(l=8, r=8, t=4, b=4),
        plot_bgcolor="white",
        showlegend=False,
    )
    return fig


@callback(
    Output("chart-coverage-hist", "figure"),
    Input("conf-toggle", "value"),
    Input("virus-select", "value"),
)
def update_coverage_hist(conf_mode, virus_filter):
    if conf_mode == "high":
        df = ALL_DATA.copy()
        df["Confidence"] = pd.Series(df.index.isin(HC_DATA.index)).map({True: "High", False: "Low"})
    else:
        df = ALL_DATA.copy()
        df["Confidence"] = "All"

    if virus_filter:
        df = df[df["Adjusted_Species"].isin(virus_filter)]

    if df.empty:
        return go.Figure()

    fig = go.Figure()
    for conf, color in [("High", "#27ae60"), ("Low", "#e74c3c")]:
        sub = df[df["Confidence"] == conf]
        if not sub.empty:
            fig.add_trace(go.Histogram(
                x=sub["Rep_Coverage(%)"], name=conf,
                marker_color=color, opacity=0.7,
                xbins=dict(start=0, end=100, size=10),
            ))

    fig.add_vline(x=50, line_dash="dash", line_color="gray", line_width=1.5,
                  annotation_text="50% threshold", annotation_position="top right")

    fig.update_layout(
        margin=dict(l=8, r=8, t=4, b=4),
        xaxis_title="Genome Coverage (%)",
        yaxis_title="Count",
        plot_bgcolor="white",
        barmode="overlay",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


@callback(
    Output("records-table-container", "children"),
    Input("conf-toggle", "value"),
    Input("virus-select", "value"),
)
def update_table(conf_mode, virus_filter):
    df = _get_filtered_df(conf_mode, virus_filter)

    display_cols = {
        "Sample": "Sample",
        "host_species": "Host Species",
        "host_clade": "Host Clade",
        "host_family": "Host Family",
        "host_order": "Host Order",
        "host_tissue": "Tissue",
        "Adjusted_Species": "Virus Species",
        "Rep_Coverage(%)": "Coverage %",
        "Rep_MeanDepth": "Mean Depth",
        "Asm_EM_Reads": "EM Reads",
        "Asm_TPM": "TPM",
        "Asm_Rel_Abund(%)": "Rel Abund %",
        "Molecule_type": "Molecule Type",
        "Rep_Length": "Ref Length",
        "Avg_Read_ANI": "Avg ANI",
        "Predicted_Support": "Support",
    }
    available = [k for k in display_cols if k in df.columns]

    table = dash_table.DataTable(
        data=df[available].to_dict("records"),
        columns=[{"name": display_cols.get(c, c), "id": c} for c in available],
        page_size=50,
        page_action="native",
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto", "minWidth": "100%"},
        style_cell={
            "fontSize": "12px", "padding": "6px 8px", "textAlign": "left",
            "fontFamily": "Inter, sans-serif", "minWidth": "80px",
        },
        style_header={"backgroundColor": "#f1f3f5", "fontWeight": "bold", "fontSize": "12px"},
        style_data_conditional=[
            {
                "if": {"filter_query": "{Rep_Coverage(%)} >= 50 && {Rep_MeanDepth} >= 5"},
                "backgroundColor": "rgba(39,174,96,0.06)",
            },
        ],
    )
    return table


# ── Host-aware chart callbacks ──
@callback(
    Output("chart-clade-virus", "figure"),
    Input("conf-toggle", "value"),
    Input("virus-select", "value"),
)
def update_clade_virus(conf_mode, virus_filter):
    df = _get_filtered_df(conf_mode, virus_filter)
    if "host_clade" not in df.columns or df["host_clade"].eq("").all():
        return go.Figure()
    cv = df.groupby("host_clade")["Adjusted_Species"].nunique().sort_values(ascending=True).tail(15)
    if cv.empty:
        return go.Figure()
    fig = go.Figure(go.Bar(
        x=cv.values, y=cv.index, orientation="h",
        marker=dict(color=cv.values, colorscale="Oranges", showscale=False,
                    line=dict(color="rgba(0,0,0,0.1)", width=0.5)),
        text=cv.values, textposition="outside",
        hovertemplate="%{y}<br>Virus species: %{x}<extra></extra>",
    ))
    fig.update_layout(
        margin=dict(l=8, r=30, t=4, b=4),
        xaxis_title="Unique Virus Species Detected",
        plot_bgcolor="white", bargap=0.3,
    )
    return fig


@callback(
    Output("chart-host-family", "figure"),
    Input("conf-toggle", "value"),
    Input("virus-select", "value"),
)
def update_host_family(conf_mode, virus_filter):
    df = _get_filtered_df(conf_mode, virus_filter)
    if "host_family" not in df.columns or df["host_family"].eq("").all():
        return go.Figure()
    fc = df.groupby("host_family")["Sample"].nunique().sort_values(ascending=True).tail(15)
    if fc.empty:
        return go.Figure()
    fig = go.Figure(go.Bar(
        x=fc.values, y=fc.index, orientation="h",
        marker=dict(color=fc.values, colorscale="Reds", showscale=False,
                    line=dict(color="rgba(0,0,0,0.1)", width=0.5)),
        text=fc.values, textposition="outside",
        hovertemplate="%{y}<br>Infected samples: %{x}<extra></extra>",
    ))
    fig.update_layout(
        margin=dict(l=8, r=30, t=4, b=4),
        xaxis_title="Virus-Positive Samples",
        plot_bgcolor="white", bargap=0.3,
    )
    return fig


@callback(
    Output("chart-virus-host-heatmap", "figure"),
    Input("conf-toggle", "value"),
    Input("virus-select", "value"),
)
def update_virus_host_heatmap(conf_mode, virus_filter):
    df = _get_filtered_df(conf_mode, virus_filter)
    if "host_family" not in df.columns or df["host_family"].eq("").all():
        return go.Figure()
    # Top 12 viruses × Top 10 host families
    top_v = df.groupby("Adjusted_Species")["Sample"].nunique().nlargest(12).index
    top_f = df.groupby("host_family")["Sample"].nunique().nlargest(10).index
    sub = df[df["Adjusted_Species"].isin(top_v) & df["host_family"].isin(top_f)]
    if sub.empty:
        return go.Figure()
    mat = sub.pivot_table(index="Adjusted_Species", columns="host_family",
                          values="Sample", aggfunc="nunique", fill_value=0)
    fig = go.Figure(go.Heatmap(
        z=mat.values, x=mat.columns.tolist(), y=mat.index.tolist(),
        colorscale="YlOrRd", text=mat.values, texttemplate="%{text}",
        hovertemplate="Virus: %{y}<br>Family: %{x}<br>Samples: %{z}<extra></extra>",
        colorbar=dict(title="Samples", thickness=12),
    ))
    fig.update_layout(
        margin=dict(l=8, r=8, t=4, b=8),
        xaxis=dict(tickfont=dict(size=9), tickangle=30),
        yaxis=dict(tickfont=dict(size=10)),
        plot_bgcolor="white",
    )
    return fig


@callback(
    Output("chart-tissue-dist", "figure"),
    Input("conf-toggle", "value"),
    Input("virus-select", "value"),
)
def update_tissue_dist(conf_mode, virus_filter):
    df = _get_filtered_df(conf_mode, virus_filter)
    if "host_tissue" not in df.columns or df["host_tissue"].eq("").all():
        return go.Figure()
    # Normalize tissue names
    def simplify_tissue(t):
        t = str(t).strip().lower()
        if "leaf" in t or "leaves" in t:
            return "Leaf / Leaves"
        if "algal" in t or "algae" in t:
            return "Algal Cells"
        if "flower" in t or "floral" in t or "bud" in t:
            return "Flower / Bud"
        if "root" in t:
            return "Root"
        if "shoot" in t or "stem" in t:
            return "Shoot / Stem"
        if "fruit" in t:
            return "Fruit"
        if "seed" in t:
            return "Seed / Seedling"
        if "gametophyte" in t:
            return "Gametophyte"
        if "whole plant" in t or "whole shoot" in t:
            return "Whole Plant/Shoot"
        if "sporo" in t:
            return "Sporophyte"
        return "Other"
    df["tissue_cat"] = df["host_tissue"].apply(simplify_tissue)
    tc = df.groupby("tissue_cat")["Sample"].nunique().sort_values(ascending=True)
    if tc.empty:
        return go.Figure()
    fig = go.Figure(go.Bar(
        x=tc.values, y=tc.index, orientation="h",
        marker=dict(color=tc.values, colorscale="Greens", showscale=False,
                    line=dict(color="rgba(0,0,0,0.1)", width=0.5)),
        text=tc.values, textposition="outside",
        hovertemplate="%{y}<br>Samples: %{x}<extra></extra>",
    ))
    fig.update_layout(
        margin=dict(l=8, r=30, t=4, b=4),
        xaxis_title="Infected Samples",
        plot_bgcolor="white", bargap=0.3,
    )
    return fig


# ═══════════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8051))
    print(f"1KP Virome Dashboard → http://localhost:{port}/onekp/")
    app.run(debug=False, host="127.0.0.1", port=port, dev_tools_ui=False)
