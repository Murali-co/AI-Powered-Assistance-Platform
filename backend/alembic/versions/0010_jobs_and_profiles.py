"""Add job_postings and verified_profiles tables

Revision ID: 0010_jobs_and_profiles
Revises: 0009_update_default_model
Create Date: 2026-10-21 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0010_jobs_and_profiles'
down_revision = '0009_update_default_model'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    # 1. Create job_postings if not exists
    if 'job_postings' not in tables:
        op.create_table(
            'job_postings',
            sa.Column('id', sa.String(), primary_key=True),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('normalized_title', sa.String(), nullable=True),
            sa.Column('company', sa.String(), nullable=False),
            sa.Column('location', sa.String(), nullable=True),
            sa.Column('job_type', sa.String(), nullable=True, server_default='onsite'),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('required_skills', sa.Text(), nullable=True, server_default='[]'),
            sa.Column('preferred_skills', sa.Text(), nullable=True, server_default='[]'),
            sa.Column('min_years_experience', sa.Integer(), nullable=True),
            sa.Column('education_level', sa.String(), nullable=True),
            sa.Column('source_url', sa.String(), nullable=True),
            sa.Column('source_id', sa.String(), nullable=True),
            sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_verified_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
        )
        op.create_index('ix_job_postings_id', 'job_postings', ['id'])
        op.create_index('ix_job_postings_normalized_title', 'job_postings', ['normalized_title'])
        op.create_index('ix_job_postings_source_id', 'job_postings', ['source_id'])

    # 2. Create verified_profiles if not exists
    if 'verified_profiles' not in tables:
        op.create_table(
            'verified_profiles',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True),
            sa.Column('skills', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('work_experience', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('education', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('projects', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('certifications', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('consent_settings', sa.Text(), nullable=False, server_default='{"local_only": true, "external_ai": false}'),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now())
        )
        op.create_index('ix_verified_profiles_id', 'verified_profiles', ['id'])
        op.create_index('ix_verified_profiles_user_id', 'verified_profiles', ['user_id'])

    # 3. Add difficulty and interview_type columns to interview_sessions if missing
    if 'interview_sessions' in tables:
        session_cols = [c['name'] for c in insp.get_columns('interview_sessions')]
        if 'difficulty_level' not in session_cols:
            op.add_column('interview_sessions', sa.Column('difficulty_level', sa.Integer(), nullable=True, server_default='2'))
        if 'interview_type' not in session_cols:
            op.add_column('interview_sessions', sa.Column('interview_type', sa.String(), nullable=True, server_default='mixed'))
        if 'topics_covered' not in session_cols:
            op.add_column('interview_sessions', sa.Column('topics_covered', sa.Text(), nullable=True, server_default='[]'))


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'verified_profiles' in tables:
        op.drop_table('verified_profiles')
    if 'job_postings' in tables:
        op.drop_table('job_postings')
