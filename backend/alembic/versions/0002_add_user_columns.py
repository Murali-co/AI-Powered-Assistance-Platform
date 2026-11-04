"""Add preferred_model and last_active_at to users table

Revision ID: 0002_add_user_columns
Revises: 0001_initial
Create Date: 2026-06-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0002_add_user_columns'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to users table
    op.add_column('users', sa.Column('preferred_model', sa.String(length=50), nullable=True, server_default='qwen3:14b'))
    op.add_column('users', sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # Remove columns if downgrading
    op.drop_column('users', 'last_active_at')
    op.drop_column('users', 'preferred_model')
