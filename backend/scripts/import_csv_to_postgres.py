"""Import CSV files exported from SQLite into PostgreSQL using COPY."""
import os
import psycopg
from app.config import settings
from pathlib import Path

DATA_DIR = Path("./data/sqlite_export")

DSN = os.environ.get('DATABASE_URL', settings.DATABASE_URL)

COPY_MAP = {
    'users': ['id','email','hashed_password','full_name','created_at'],
    'applications_history': ['id','user_id','job_id','job_title','company','applied_at','status','cover_letter','resume_bullets','notes'],
    'user_criteria': ['user_id','title','location','is_remote','hours_old'],
    'chat_messages': ['id','session_id','user_id','role','content','created_at'],
    'interview_sessions': ['id','user_id','job_id','target_role','created_at','is_finished','chat_history','feedback','score'],
    'resume_versions': ['id','user_id','resume_text','version_label','created_at'],
    'notifications': ['id','user_id','title','message','type','is_read','created_at'],
}


def import_table(table_name):
    csv_file = DATA_DIR / f"{table_name}.csv"
    if not csv_file.exists():
        print(f"CSV for {table_name} not found, skipping")
        return
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            with open(csv_file, 'r') as f:
                # skip header
                next(f)
                cur.copy(f"COPY {table_name}({', '.join(COPY_MAP[table_name])}) FROM STDIN WITH CSV", f)
        conn.commit()
        print(f"Imported {table_name}")


if __name__ == '__main__':
    for t in COPY_MAP.keys():
        try:
            import_table(t)
        except Exception as e:
            print(f"Failed to import {t}: {e}")
