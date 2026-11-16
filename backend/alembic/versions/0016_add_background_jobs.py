"""Add background_jobs persistent table for background job lifecycle

Revision ID: 0016_add_background_jobs
Revises: 0015_sync_all_models
Create Date: 2026-10-31 10:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
import logging

# revision identifiers, used by Alembic.
revision = '0016_add_background_jobs'
down_revision = '0015_sync_all_models'
branch_labels = None
depends_on = None

logger = logging.getLogger('alembic.runtime.migration')


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'background_jobs' not in tables:
        op.create_table(
            'background_jobs',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
            sa.Column('job_type', sa.String(length=50), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('worker_id', sa.String(length=100), nullable=True),
            sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('result', sa.JSON(), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_background_jobs_id', 'background_jobs', ['id'])
        op.create_index('ix_background_jobs_user_id', 'background_jobs', ['user_id'])
        op.create_index('ix_background_jobs_job_type', 'background_jobs', ['job_type'])
        op.create_index('ix_background_jobs_status', 'background_jobs', ['status'])
        op.create_index('ix_background_jobs_worker_id', 'background_jobs', ['worker_id'])
        op.create_index('ix_background_jobs_expires_at', 'background_jobs', ['expires_at'])


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'background_jobs' in tables:
        # Non-destructive downgrade check: verify if records exist
        try:
            result = conn.execute(sa.text("SELECT COUNT(*) FROM background_jobs")).scalar()
            if result == 0:
                op.drop_table('background_jobs')
            else:
                logger.warning(
                    "Skipping destructive drop of 'background_jobs' because it contains %d active records.", result
                )
        except Exception as e:
            logger.error("Error inspecting background_jobs row count during downgrade: %s", e)
