"""Export SQLite data to CSV files for import into PostgreSQL."""
import sqlite3
import csv
from app.config import settings
from pathlib import Path

OUT_DIR = Path("./data/sqlite_export")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def export_table(table_name, cols=None):
    conn = sqlite3.connect(settings.SQLITE_PATH)
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    col_names = [d[0] for d in cursor.description]
    with open(OUT_DIR / f"{table_name}.csv", "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(col_names)
        writer.writerows(rows)
    conn.close()

if __name__ == '__main__':
    tables = [
        'users', 'applications_history', 'user_criteria', 'chat_messages',
        'interview_sessions', 'resume_versions', 'notifications'
    ]
    for t in tables:
        try:
            export_table(t)
            print(f"Exported {t}")
        except Exception as e:
            print(f"Failed to export {t}: {e}")
