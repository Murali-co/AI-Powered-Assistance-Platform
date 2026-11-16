"""Update default model to qwen3:14b

Revision ID: 0009_update_default_model
Revises: 0008_add_interview_mode
Create Date: 2026-10-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0009_update_default_model'
down_revision = '0008_add_interview_mode'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('users')]
    if 'preferred_model' in cols:
        # Update existing records pointing to older qwen2.5 models
        conn.execute(
            sa.text("UPDATE users SET preferred_model = 'qwen3:14b' WHERE preferred_model LIKE 'qwen2%' OR preferred_model IS NULL")
        )
        try:
            op.alter_column('users', 'preferred_model', server_default='qwen3:14b')
        except Exception:
            # SQLite does not support ALTER COLUMN server_default directly
            pass


def downgrade():
    try:
        op.alter_column('users', 'preferred_model', server_default='qwen2.5:7b')
    except Exception:
        pass
