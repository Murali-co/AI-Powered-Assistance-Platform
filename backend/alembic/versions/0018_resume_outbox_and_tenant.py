"""Add resume indexing outbox, sections, skills and tenant compound indexes

Revision ID: 0018_resume_outbox_and_tenant
Revises: 0017_ensure_app_history
Create Date: 2026-11-15 10:30:00.000000

"""
import logging
from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision = '0018_resume_outbox_and_tenant'
down_revision = '0017_ensure_app_history'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    # 1. Update resume_versions with active pointer and indexing lifecycle columns
    if 'resume_versions' in tables:
        existing_cols = {c['name'] for c in insp.get_columns('resume_versions')}
        with op.batch_alter_table('resume_versions') as batch_op:
            if 'is_active' not in existing_cols:
                batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default='false'))
            if 'indexing_status' not in existing_cols:
                batch_op.add_column(sa.Column('indexing_status', sa.String(length=32), nullable=False, server_default='completed'))
            if 'embedding_id' not in existing_cols:
                batch_op.add_column(sa.Column('embedding_id', sa.String(length=64), nullable=True))

        # Compound index for fast tenant active resume retrieval
        existing_indexes = {ix['name'] for ix in insp.get_indexes('resume_versions')}
        if 'ix_resume_versions_user_active' not in existing_indexes:
            op.create_index('ix_resume_versions_user_active', 'resume_versions', ['user_id', 'is_active'])

    # 2. Create resume_sections table
    if 'resume_sections' not in tables:
        op.create_table(
            'resume_sections',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('resume_version_id', sa.Integer(), sa.ForeignKey('resume_versions.id', ondelete='CASCADE'), nullable=False),
            sa.Column('section_type', sa.String(length=64), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index('ix_resume_sections_id', 'resume_sections', ['id'])
        op.create_index('ix_resume_sections_user_id', 'resume_sections', ['user_id'])
        op.create_index('ix_resume_sections_resume_version_id', 'resume_sections', ['resume_version_id'])
        op.create_index('ix_resume_sections_section_type', 'resume_sections', ['section_type'])

    # 3. Create resume_skills table
    if 'resume_skills' not in tables:
        op.create_table(
            'resume_skills',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('resume_version_id', sa.Integer(), sa.ForeignKey('resume_versions.id', ondelete='CASCADE'), nullable=False),
            sa.Column('skill_name', sa.String(length=128), nullable=False),
            sa.Column('category', sa.String(length=64), nullable=True),
            sa.Column('years_experience', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index('ix_resume_skills_id', 'resume_skills', ['id'])
        op.create_index('ix_resume_skills_user_id', 'resume_skills', ['user_id'])
        op.create_index('ix_resume_skills_resume_version_id', 'resume_skills', ['resume_version_id'])
        op.create_index('ix_resume_skills_skill_name', 'resume_skills', ['skill_name'])

    # 4. Create resume_indexing_outbox table
    if 'resume_indexing_outbox' not in tables:
        op.create_table(
            'resume_indexing_outbox',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('resume_version_id', sa.Integer(), sa.ForeignKey('resume_versions.id', ondelete='CASCADE'), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('ix_resume_indexing_outbox_id', 'resume_indexing_outbox', ['id'])
        op.create_index('ix_resume_indexing_outbox_user_id', 'resume_indexing_outbox', ['user_id'])
        op.create_index('ix_resume_indexing_outbox_resume_version_id', 'resume_indexing_outbox', ['resume_version_id'])
        op.create_index('ix_resume_indexing_outbox_status', 'resume_indexing_outbox', ['status'])
        op.create_index('ix_resume_outbox_user_status', 'resume_indexing_outbox', ['user_id', 'status'])


def downgrade():
    logger.warning("Downgrade for 0018 requested. Non-destructive preserving user data.")
