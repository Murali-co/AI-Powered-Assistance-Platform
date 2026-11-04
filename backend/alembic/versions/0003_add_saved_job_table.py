"""Add SavedJob table

Revision ID: 0003_add_saved_job_table
Revises: 0002_add_user_columns
Create Date: 2026-06-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0003_add_saved_job_table'
down_revision = '0002_add_user_columns'
branch_labels = None
depends_on = None


def upgrade():
    # Create saved_jobs table
    op.create_table(
        'saved_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('job_title', sa.String(), nullable=False),
        sa.Column('company', sa.String(), nullable=False),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('job_url', sa.String(), nullable=True),
        sa.Column('saved_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_saved_jobs_user_id', 'user_id')
    )


def downgrade():
    # Drop saved_jobs table
    op.drop_table('saved_jobs')
