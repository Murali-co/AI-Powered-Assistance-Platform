"""Add interview_mode column to interview_sessions

Revision ID: 0008_add_interview_mode
Revises: 0007_2fa_and_backup_codes
Create Date: 2026-08-18 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0008_add_interview_mode'
down_revision = '0007_2fa_and_backup_codes'
branch_labels = None
depends_on = None


def upgrade():
    # Add interview_mode column if it doesn't exist already
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('interview_sessions')]
    if 'interview_mode' not in cols:
        op.add_column('interview_sessions', sa.Column('interview_mode', sa.String(), nullable=True))


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns('interview_sessions')]
    if 'interview_mode' in cols:
        op.drop_column('interview_sessions', 'interview_mode')
