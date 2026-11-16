"""Ensure applications_history and application_status_history tables exist idempotently

Revision ID: 0017_ensure_applications_history_table
Revises: 0016_add_background_jobs
Create Date: 2026-10-31 12:00:00.000000

PROPOSAL AWAITING ADMINISTRATOR APPROVAL:
This migration is non-destructive and idempotent. It creates applications_history
and application_status_history if missing, or adds missing columns if already present,
preserving all existing production data.
DO NOT EXECUTE AUTOMATICALLY AGAINST PRODUCTION NEON POSTGRESQL WITHOUT APPROVAL.
"""
import logging
from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision = '0017_ensure_app_history'
down_revision = '0016_add_background_jobs'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    # 1. Verify / Create applications_history table
    if 'applications_history' not in tables:
        logger.info("Creating missing 'applications_history' table...")
        op.create_table(
            'applications_history',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('job_id', sa.String(), nullable=False),
            sa.Column('job_title', sa.String(), nullable=False),
            sa.Column('company', sa.String(), nullable=False),
            sa.Column('applied_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('status', sa.String(), nullable=False, server_default='applied'),
            sa.Column('cover_letter', sa.Text(), nullable=False, server_default=''),
            sa.Column('resume_bullets', sa.Text(), nullable=False, server_default=''),
            sa.Column('notes', sa.Text(), nullable=False, server_default=''),
            sa.Column('location', sa.String(), nullable=True),
            sa.Column('job_url', sa.String(), nullable=True),
            sa.Column('resume_version_id', sa.Integer(), nullable=True),
            sa.Column('tone', sa.String(), nullable=True),
        )
        op.create_index('ix_applications_history_id', 'applications_history', ['id'], unique=False)
        op.create_index('ix_applications_history_user_id', 'applications_history', ['user_id'], unique=False)
    else:
        logger.info("'applications_history' table exists; verifying column synchronization...")
        existing_cols = {c['name'] for c in insp.get_columns('applications_history')}
        with op.batch_alter_table('applications_history') as batch_op:
            if 'location' not in existing_cols:
                batch_op.add_column(sa.Column('location', sa.String(), nullable=True))
            if 'job_url' not in existing_cols:
                batch_op.add_column(sa.Column('job_url', sa.String(), nullable=True))
            if 'resume_version_id' not in existing_cols:
                batch_op.add_column(sa.Column('resume_version_id', sa.Integer(), nullable=True))
            if 'tone' not in existing_cols:
                batch_op.add_column(sa.Column('tone', sa.String(), nullable=True))

    # Re-check table names in case transaction state updated
    tables = sa.inspect(conn).get_table_names()

    # 2. Verify / Create application_status_history table
    if 'application_status_history' not in tables:
        logger.info("Creating missing 'application_status_history' table...")
        op.create_table(
            'application_status_history',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('application_id', sa.String(), sa.ForeignKey('applications_history.id', ondelete='CASCADE'), nullable=False),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_application_status_history_id', 'application_status_history', ['id'], unique=False)
        op.create_index('ix_application_status_history_application_id', 'application_status_history', ['application_id'], unique=False)
    else:
        logger.info("'application_status_history' table already exists; verifying columns...")
        existing_status_cols = {c['name'] for c in insp.get_columns('application_status_history')}
        with op.batch_alter_table('application_status_history') as batch_op:
            if 'changed_at' not in existing_status_cols:
                batch_op.add_column(sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))


def downgrade():
    logger.warning("Downgrade for 0017 requested. Preserving applications_history to prevent data loss.")
