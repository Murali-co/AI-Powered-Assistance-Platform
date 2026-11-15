"""Add adaptive interview session columns, resume target roles, and career milestones

Revision ID: 0011_adaptive_career
Revises: 0010_jobs_and_profiles
Create Date: 2026-10-21 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic (<= 32 characters)
revision = '0011_adaptive_career'
down_revision = '0010_jobs_and_profiles'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    # 1. Update interview_sessions with adaptive difficulty and topic tracking columns
    if 'interview_sessions' in tables:
        existing_cols = [c['name'] for c in insp.get_columns('interview_sessions')]
        if 'difficulty_level' not in existing_cols:
            op.add_column(
                'interview_sessions',
                sa.Column('difficulty_level', sa.Integer(), nullable=False, server_default='3')
            )
        if 'topics_covered' not in existing_cols:
            op.add_column(
                'interview_sessions',
                sa.Column('topics_covered', sa.Text(), nullable=False, server_default='[]')
            )
        if 'metadata_json' not in existing_cols:
            op.add_column(
                'interview_sessions',
                sa.Column('metadata_json', sa.Text(), nullable=True)
            )

    # 2. Update resume_versions with target_role and structured_data
    if 'resume_versions' in tables:
        existing_rv_cols = [c['name'] for c in insp.get_columns('resume_versions')]
        if 'target_role' not in existing_rv_cols:
            op.add_column(
                'resume_versions',
                sa.Column('target_role', sa.String(), nullable=True)
            )
        if 'structured_data' not in existing_rv_cols:
            op.add_column(
                'resume_versions',
                sa.Column('structured_data', sa.Text(), nullable=True)
            )

    # 3. Create career_milestones table
    if 'career_milestones' not in tables:
        op.create_table(
            'career_milestones',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('target_role', sa.String(), nullable=False),
            sa.Column('skill_name', sa.String(), nullable=False),
            sa.Column('importance', sa.String(), nullable=True, server_default='core'),
            sa.Column('current_proficiency', sa.String(), nullable=True, server_default='beginner'),
            sa.Column('target_proficiency', sa.String(), nullable=True, server_default='proficient'),
            sa.Column('resources', sa.Text(), nullable=True, server_default='[]'),
            sa.Column('exercises', sa.Text(), nullable=True, server_default='[]'),
            sa.Column('status', sa.String(), nullable=False, server_default='pending'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())
        )
        op.create_index('ix_career_milestones_id', 'career_milestones', ['id'])
        op.create_index('ix_career_milestones_user_id', 'career_milestones', ['user_id'])


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'career_milestones' in tables:
        op.drop_table('career_milestones')

    if 'resume_versions' in tables:
        existing_rv_cols = [c['name'] for c in insp.get_columns('resume_versions')]
        if 'structured_data' in existing_rv_cols:
            op.drop_column('resume_versions', 'structured_data')
        if 'target_role' in existing_rv_cols:
            op.drop_column('resume_versions', 'target_role')

    if 'interview_sessions' in tables:
        existing_cols = [c['name'] for c in insp.get_columns('interview_sessions')]
        if 'metadata_json' in existing_cols:
            op.drop_column('interview_sessions', 'metadata_json')
        if 'topics_covered' in existing_cols:
            op.drop_column('interview_sessions', 'topics_covered')
        if 'difficulty_level' in existing_cols:
            op.drop_column('interview_sessions', 'difficulty_level')
