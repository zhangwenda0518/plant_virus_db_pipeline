"""
Import predictions_v7_annotated.json into SQLite database.
Creates predictions_v7 table with full multi-algorithm fields.
"""
import json, sqlite3, sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "pamirdb.sqlite"
PRED_FILE = DATA_DIR / "predictions_v7_annotated.json"


def import_predictions():
    print(f"Loading: {PRED_FILE}")
    with open(PRED_FILE) as f:
        data = json.load(f)

    results = data.get("results", data if isinstance(data, list) else [])
    print(f"Predictions: {len(results)}")
    if not results:
        print("No data!")
        return

    # All fields from v7 (40+ columns)
    columns = sorted(results[0].keys())
    print(f"Columns ({len(columns)}): {columns}")

    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")

    # Drop old v7 table if exists, create new
    db.execute("DROP TABLE IF EXISTS predictions_v7")

    # Map Python types to SQLite
    type_map = {str: "TEXT", int: "INTEGER", float: "REAL", bool: "INTEGER"}
    col_defs = []
    for c in columns:
        sample_val = results[0].get(c)
        sql_type = type_map.get(type(sample_val), "TEXT")
        col_defs.append('"' + c + '" ' + sql_type)

    create_sql = f'CREATE TABLE predictions_v7 (id INTEGER PRIMARY KEY AUTOINCREMENT, {", ".join(col_defs)})'
    db.execute(create_sql)

    # Batch insert
    placeholders = ", ".join(["?" for _ in columns])
    col_names = ", ".join('"' + c + '"' for c in columns)
    insert_sql = f'INSERT INTO predictions_v7 ({col_names}) VALUES ({placeholders})'

    batch = []
    for r in results:
        batch.append([r.get(c) for c in columns])
        if len(batch) >= 500:
            db.executemany(insert_sql, batch)
            batch = []

    if batch:
        db.executemany(insert_sql, batch)

    db.commit()

    # Create indexes
    db.execute("CREATE INDEX IF NOT EXISTS idx_pv7_mirna ON predictions_v7(mirna_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_pv7_virus ON predictions_v7(target_virus_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_pv7_family ON predictions_v7(target_virus_family)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_pv7_level ON predictions_v7(consensus_level)")

    count = db.execute("SELECT COUNT(*) FROM predictions_v7").fetchone()[0]
    db.close()

    print(f"\nImported: {count} predictions")
    print(f"DB: {DB_PATH}")
    print("Done!")


if __name__ == "__main__":
    import_predictions()
