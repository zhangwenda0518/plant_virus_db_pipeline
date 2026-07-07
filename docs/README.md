# Plant Virus Reference Database - Web Interface

Interactive searchable table for the plant virus reference database.

## Setup

1. Copy the latest data file:
```bash
cp G-cluster/Plant_Virus_Ref.Info.tsv web_db/data/
```

2. Enable GitHub Pages in repo Settings:
   - Source: `main` branch
   - Folder: `/web_db`

3. Visit `https://zhangwenda0518.github.io/plant_virus_db_pipeline/`

## Auto-update via GitHub Actions (optional)

Create `.github/workflows/update_db.yml` to automatically copy the latest
data file when the web_db branch updates.
