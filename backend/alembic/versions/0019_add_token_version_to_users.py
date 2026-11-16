"""Add token_version to users for instant access token revocation

Revision ID: 0019_add_token_version_to_users
Revises: 0018_resume_outbox_and_tenant
Create Date: 2026-11-15 11:20:00.000000

"""
import logging
from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision = '0019_add_token_version_to_users'
down_revision = '0018_resume_outbox_and_tenant'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'users' in tables:
        existing_cols = {c['name'] for c in insp.get_columns('users')}
        if 'token_version' not in existing_cols:
            op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='1'))
            logger.info("Added token_version column to users table")


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'users' in tables:
        existing_cols = {c['name'] for c in insp.get_columns('users')}
        if 'token_version' in existing_cols:
            op.drop_column('users', 'token_version')
            logger.info("Dropped token_version column from users table")
