import dash
from dash import dcc, html, Input, Output, State, dash_table, callback
import dash_mantine_components as dmc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import os

# =============================================================================
# 1. 加载真实植物病毒参考数据库
# =============================================================================

DATA_URL = "https://raw.githubusercontent.com/zhangwenda0518/plant_virus_db_pipeline/main/docs/data/final.cluster.ref_info.tsv"


def load_data():
    df = pd.read_csv(DATA_URL, sep='\t', low_memory=False)
    # Extract year from Release_Date / Collection_Date
    df['Year'] = df['Release_Date'].astype(str).str.extract(r'(\d{4})')[0]
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(2020).astype(int)
    # Clean up columns
    df['Organism'] = df['Species_ICTV'].fillna(df['Species_NCBI']).fillna('Unknown')
    df['Country'] = df['Geo_Location'].fillna('Unknown')
    df['Family'] = df['VMR_Family'].fillna('Unknown')
    df['Genus'] = df['VMR_Genus'].fillna('Unknown')
    df['Host_Name'] = df['Host'].fillna('Unknown')
    df['Category_Type'] = df['Category'].str.split('_').str[0].fillna('Unknown')
    return df


try:
    df_global = load_data()
except Exception as e:
    print(f"Data load failed: {e}, using empty dataframe")
    df_global = pd.DataFrame(columns=['Organism','Family','Genus','Category','Host_Name','Country','Year','Molecule_type','Topology','Length','Category_Type','Accession','GenBank_Title'])

# =============================================================================
# 2. UI 布局
# =============================================================================

app = dash.Dash(__name__, external_stylesheets=[
    "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap"
])
server = app.server  # for gunicorn
app.title = "Plant Virus Reference Database — Interactive Explorer"

app.layout = dmc.MantineProvider(
    theme={"fontFamily": "Inter, sans-serif", "primaryColor": "teal"},
    children=dmc.AppShell(
        header={"height": 60},
        padding="md",
        children=[
            dmc.AppShellHeader(
                px="md",
                children=dmc.Group(
                    justify="space-between", h="100%",
                    children=[
                        dmc.Group(children=[
                            dmc.Text("🧬", size="xl"),
                            dmc.Title("Plant Virus Reference Explorer", order=3, style={"fontWeight": 700})
                        ]),
                        dmc.Group(children=[
                            dmc.Badge(str(len(df_global)) + " sequences", color="teal", variant="light"),
                            dmc.Badge(str(df_global['Organism'].nunique()) + " species", color="indigo", variant="light"),
                            dmc.Anchor("← Back to Database", href="https://zhangwenda0518.github.io/plant_virus_db_pipeline/",
                                      size="sm", underline=False)
                        ])
                    ]
                )
            ),

            dmc.AppShellMain(children=dmc.Grid(gutter="md", children=[
                # Left panel: filters
                dmc.GridCol(span={"base": 12, "md": 3}, children=dmc.Paper(
                    withBorder=True, shadow="sm", p="md", radius="md", children=[
                        dmc.Title("Filters", order=4, mb="md"),

                        dmc.TextInput(id="host-filter", label="Host (e.g. Capsicum, Solanum)",
                                      placeholder="Capsicum", mb="sm"),

                        dmc.MultiSelect(id="family-filter", label="Virus Family",
                                        data=sorted([{"value": v, "label": v}
                                               for v in df_global['Family'].unique() if v != 'Unknown'],
                                              key=lambda x: x['label']),
                                        placeholder="All families", mb="sm", searchable=True, clearable=True),

                        dmc.MultiSelect(id="category-filter", label="Category",
                                        data=[{"value": "Segmented", "label": "Segmented"},
                                              {"value": "NonSegmented", "label": "Non‑Segmented"}],
                                        value=["Segmented", "NonSegmented"], mb="sm"),

                        dmc.MultiSelect(id="genome-filter", label="Genome Type",
                                        data=sorted([{"value": v, "label": v}
                                               for v in df_global['Molecule_type'].dropna().unique()],
                                              key=lambda x: x['label']),
                                        placeholder="All types", mb="sm", searchable=True, clearable=True),

                        dmc.Text("Release Year Range", size="sm", fw=600, mb="xs"),
                        html.Div(
                            dcc.RangeSlider(
                                id="year-slider",
                                min=df_global['Year'].min(), max=df_global['Year'].max(), step=1,
                                value=[df_global['Year'].min(), df_global['Year'].max()],
                                marks={y: {"label": str(y), "style": {"fontSize": "10px"}}
                                       for y in range(1990, 2026, 5)},
                                allowCross=False,
                                tooltip={"placement": "bottom", "always_visible": True}
                            ),
                            style={"padding": "0 20px 10px 20px"}
                        ),

                        dmc.Divider(my="md"),

                        dmc.Button("Apply Filters", id="apply-btn", color="teal", fullWidth=True,
                                   radius="md", leftSection="🔍")
                    ]
                )),

                # Right panel: charts + table
                dmc.GridCol(span={"base": 12, "md": 9}, children=dmc.Paper(
                    withBorder=True, shadow="sm", p="md", radius="md", children=[
                        dmc.Tabs(value="trends", children=[
                            dmc.TabsList(mb="md", children=[
                                dmc.TabsTab("Spatiotemporal", value="trends", leftSection="📊"),
                                dmc.TabsTab("Mutation/Alignment", value="mutation", leftSection="🧬"),
                                dmc.TabsTab("Taxonomy", value="taxonomy", leftSection="🦠"),
                                dmc.TabsTab("Data Table", value="table", leftSection="📋")
                            ]),

                            # Spatiotemporal tab — faceted bar chart by country × year × species
                            dmc.TabsPanel(value="trends", children=[
                                dmc.Group(justify="space-between", mb="md", children=[
                                    dmc.Title("Spatiotemporal Distribution", order=3),
                                    dmc.Badge(id="stats-badge", color="gray")
                                ]),
                                dmc.Grid(gutter="md", children=[
                                    dmc.GridCol(span=4, children=dmc.Card(
                                        withBorder=True, shadow="xs", p="sm", radius="md",
                                        children=[dmc.Text("Sample Size", size="xs", c="dimmed"),
                                                  dmc.Title(id="kpi-seqs", order=3, c="teal")]
                                    )),
                                    dmc.GridCol(span=4, children=dmc.Card(
                                        withBorder=True, shadow="xs", p="sm", radius="md",
                                        children=[dmc.Text("Species", size="xs", c="dimmed"),
                                                  dmc.Title(id="kpi-species", order=3, c="indigo")]
                                    )),
                                    dmc.GridCol(span=4, children=dmc.Card(
                                        withBorder=True, shadow="xs", p="sm", radius="md",
                                        children=[dmc.Text("Regions", size="xs", c="dimmed"),
                                                  dmc.Title(id="kpi-countries", order=3, c="orange")]
                                    ))
                                ]),
                                dmc.Space(h="md"),
                                dcc.Loading(dcc.Graph(id="spatiotemporal-chart", style={"height": "520px"}), type="cube", color="#12b886"),
                                dmc.Space(h="md"),
                                dmc.Title("Timeline by Category", order=4, mb="xs"),
                                dcc.Loading(dcc.Graph(id="chart-timeline", style={"height": "280px"}), type="cube", color="#12b886")
                            ]),

                            # Mutation/Alignment tab
                            dmc.TabsPanel(value="mutation", children=[
                                dmc.Group(justify="space-between", mb="md", children=[
                                    dmc.Title("Category & Genome Distribution", order=3),
                                    dmc.Select(id="focus-virus-select", label="Focus Species",
                                               data=[], value="", style={"width": 380})
                                ]),
                                dmc.Grid(gutter="md", children=[
                                    dmc.GridCol(span=7, children=[
                                        dcc.Loading(dcc.Graph(id="chart-category", style={"height": "340px"}), type="cube", color="#12b886")
                                    ]),
                                    dmc.GridCol(span=5, children=[
                                        dmc.Grid(gutter="md", children=[
                                            dmc.GridCol(span=12, children=[
                                                dcc.Loading(dcc.Graph(id="chart-genome", style={"height": "250px"}), type="cube", color="#12b886")
                                            ]),
                                            dmc.GridCol(span=12, children=[
                                                dcc.Loading(dcc.Graph(id="chart-topology", style={"height": "250px"}), type="cube", color="#12b886")
                                            ])
                                        ])
                                    ])
                                ]),
                                dmc.Space(h="md"),
                                dcc.Loading(dcc.Graph(id="chart-family", style={"height": "400px"}), type="cube", color="#12b886")
                            ]),

                            # Taxonomy tab
                            dmc.TabsPanel(value="taxonomy", children=[
                                dmc.Title("Top 15 Virus Families", order=3, mb="md"),
                                dcc.Loading(dcc.Graph(id="chart-family-tax", style={"height": "400px"}), type="cube", color="#12b886"),
                                dmc.Space(h="md"),
                                dmc.Grid(gutter="md", children=[
                                    dmc.GridCol(span=6, children=[
                                        dmc.Title("Top 15 Virus Genera", order=4, mb="sm"),
                                        dcc.Loading(dcc.Graph(id="chart-genus", style={"height": "400px"}), type="cube", color="#12b886")
                                    ]),
                                    dmc.GridCol(span=6, children=[
                                        dmc.Title("Top 20 Host Plants", order=4, mb="sm"),
                                        dcc.Loading(dcc.Graph(id="chart-host", style={"height": "400px"}), type="cube", color="#12b886")
                                    ])
                                ])
                            ]),

                            # Table tab
                            dmc.TabsPanel(value="table", children=[
                                dmc.Group(justify="space-between", mb="md", children=[
                                    dmc.Title("Browse Records", order=3),
                                    dmc.Button("Export CSV", id="export-btn", size="xs", color="teal", variant="light")
                                ]),
                                dcc.Download(id="download-csv"),
                                dash_table.DataTable(
                                    id='records-table',
                                    columns=[
                                        {"name": "Accession", "id": "Accession"},
                                        {"name": "Species (ICTV)", "id": "Organism"},
                                        {"name": "Family", "id": "Family"},
                                        {"name": "Genus", "id": "Genus"},
                                        {"name": "Category", "id": "Category"},
                                        {"name": "Host", "id": "Host_Name"},
                                        {"name": "Country", "id": "Country"},
                                        {"name": "Year", "id": "Year"},
                                        {"name": "Genome", "id": "Molecule_type"},
                                        {"name": "Length", "id": "Length"}
                                    ],
                                    data=[], page_size=15,
                                    style_table={'overflowX': 'auto'},
                                    style_cell={'fontFamily': 'Inter', 'fontSize': '12px', 'padding': '8px'},
                                    style_header={'backgroundColor': '#f1f3f5', 'fontWeight': 'bold'},
                                    sort_action='native', filter_action='native'
                                )
                            ])
                        ])
                    ]
                ))
            ]))
        ])
    )


# =============================================================================
# 3. Callbacks
# =============================================================================

def filter_df(host, families, categories, genomes, years):
    df = df_global.copy()
    if host and host.strip():
        df = df[df['Host_Name'].str.contains(host.strip(), case=False, na=False)]
    if families:
        df = df[df['Family'].isin(families)]
    if categories:
        df = df[df['Category_Type'].isin(categories)]
    if genomes:
        df = df[df['Molecule_type'].isin(genomes)]
    df = df[(df['Year'] >= years[0]) & (df['Year'] <= years[1])]
    return df


@callback(
    [Output("records-table", "data"),
     Output("focus-virus-select", "data"),
     Output("focus-virus-select", "value"),
     Output("stats-badge", "children"),
     Output("kpi-seqs", "children"),
     Output("kpi-species", "children"),
     Output("kpi-countries", "children")],
    Input("apply-btn", "n_clicks"),
    [State("host-filter", "value"),
     State("family-filter", "value"),
     State("category-filter", "value"),
     State("genome-filter", "value"),
     State("year-slider", "value")]
)
def update_all(n, host, families, categories, genomes, years):
    df = filter_df(host, families, categories, genomes, years)
    seqs = f"{len(df):,}"
    spp = str(df['Organism'].nunique())
    regs = str(df['Country'].nunique())
    badge = f"{seqs} seqs | {spp} spp | {regs} regions"
    table_data = df.head(500).to_dict('records')
    virus_opts = [{"value": v, "label": v} for v in sorted(df['Organism'].unique())[:100]]
    default_v = virus_opts[0]['value'] if virus_opts else ""
    return table_data, virus_opts, default_v, badge, seqs, spp, regs


@callback(
    [Output("spatiotemporal-chart", "figure"),
     Output("chart-timeline", "figure"),
     Output("chart-category", "figure"),
     Output("chart-genome", "figure"),
     Output("chart-topology", "figure"),
     Output("chart-family", "figure"),
     Output("chart-family-tax", "figure"),
     Output("chart-genus", "figure"),
     Output("chart-host", "figure")],
    Input("apply-btn", "n_clicks"),
    [State("host-filter", "value"),
     State("family-filter", "value"),
     State("category-filter", "value"),
     State("genome-filter", "value"),
     State("year-slider", "value")]
)
def update_charts(n, host, families, categories, genomes, years):
    df = filter_df(host, families, categories, genomes, years)

    # Spatiotemporal: faceted bar by Country × Year × Virus species
    df_st = df.groupby(['Year', 'Country', 'Category_Type']).size().reset_index(name='Count')
    fig_st = px.bar(df_st, x='Year', y='Count', color='Category_Type',
                    facet_col='Country', facet_col_wrap=3,
                    color_discrete_sequence=['#2e86c1', '#e74c3c'],
                    labels={'Category_Type': 'Type'}, height=480)
    fig_st.update_yaxes(matches=None, showgrid=True, gridcolor='#f1f3f5')
    fig_st.update_layout(plot_bgcolor='white', paper_bgcolor='white',
                         legend=dict(orientation="h", yanchor="bottom", y=-0.5, xanchor="center", x=0.5),
                         margin=dict(l=40, r=20, t=30, b=120))

    # Timeline
    year_cnt = df.groupby(['Year', 'Category_Type']).size().reset_index(name='Count')
    fig_tl = px.bar(year_cnt, x='Year', y='Count', color='Category_Type',
                    color_discrete_sequence=['#2e86c1', '#e74c3c'])
    fig_tl.update_layout(plot_bgcolor='white', margin=dict(l=10, r=10, t=10, b=10))

    # Category bar
    cat_cnt = df['Category'].value_counts().reset_index()
    cat_cnt.columns = ['Category', 'Count']
    fig_cat = px.bar(cat_cnt, x='Category', y='Count', color='Category',
                     color_discrete_sequence=px.colors.qualitative.G10)
    fig_cat.update_layout(showlegend=False, plot_bgcolor='white', margin=dict(l=10, r=10, t=10, b=10))

    # Genome type
    mol_cnt = df['Molecule_type'].value_counts().reset_index()
    mol_cnt.columns = ['Genome', 'Count']
    fig_mol = px.pie(mol_cnt, names='Genome', values='Count', hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.G10)
    fig_mol.update_layout(margin=dict(l=10, r=10, t=10, b=10))

    # Topology
    topo_cnt = df['Topology'].value_counts().reset_index()
    topo_cnt.columns = ['Topology', 'Count']
    fig_topo = px.pie(topo_cnt, names='Topology', values='Count', hole=0.4,
                      color_discrete_sequence=px.colors.qualitative.Set2)
    fig_topo.update_layout(margin=dict(l=10, r=10, t=10, b=10))

    # Family — for Mutation tab
    fam_cnt = df['Family'].value_counts().head(20).reset_index()
    fam_cnt.columns = ['Family', 'Count']
    fig_fam = px.bar(fam_cnt, x='Count', y='Family', orientation='h', color_discrete_sequence=['#2e86c1'])
    fig_fam.update_layout(showlegend=False, plot_bgcolor='white', margin=dict(l=10, r=10, t=10, b=10))

    # Family — Taxonomy tab
    fam_cnt2 = df['Family'].value_counts().head(15).reset_index()
    fam_cnt2.columns = ['Family', 'Count']
    fig_famt = px.bar(fam_cnt2, x='Count', y='Family', orientation='h', color_discrete_sequence=['#2e86c1'])
    fig_famt.update_layout(showlegend=False, plot_bgcolor='white', margin=dict(l=10, r=10, t=10, b=10))

    # Genus
    gen_cnt = df['Genus'].value_counts().head(15).reset_index()
    gen_cnt.columns = ['Genus', 'Count']
    fig_gen = px.bar(gen_cnt, x='Count', y='Genus', orientation='h', color_discrete_sequence=['#27ae60'])
    fig_gen.update_layout(showlegend=False, plot_bgcolor='white', margin=dict(l=10, r=10, t=10, b=10))

    # Host
    host_cnt = df['Host_Name'].value_counts().head(20).reset_index()
    host_cnt.columns = ['Host', 'Count']
    fig_host = px.bar(host_cnt, x='Count', y='Host', orientation='h', color_discrete_sequence=['#f39c12'])
    fig_host.update_layout(showlegend=False, plot_bgcolor='white', margin=dict(l=10, r=10, t=10, b=10))

    return fig_st, fig_tl, fig_cat, fig_mol, fig_topo, fig_fam, fig_famt, fig_gen, fig_host


@callback(
    Output("download-csv", "data"),
    Input("export-btn", "n_clicks"),
    [State("host-filter", "value"),
     State("family-filter", "value"),
     State("category-filter", "value"),
     State("genome-filter", "value"),
     State("year-slider", "value")],
    prevent_initial_call=True
)
def export_csv(n, host, families, categories, genomes, years):
    df = filter_df(host, families, categories, genomes, years)
    export_cols = ['Accession', 'Organism', 'Family', 'Genus', 'Category', 'Host_Name',
                   'Country', 'Year', 'Molecule_type', 'Topology', 'Length', 'GenBank_Title']
    export = df[[c for c in export_cols if c in df.columns]]
    return dcc.send_data_frame(export.to_csv, "plant_virus_filtered.csv", index=False)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8050))
    app.run(debug=False, host="0.0.0.0", port=port)
