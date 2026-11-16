"""Add email verification columns to users table

Revision ID: 0005_email_verification
Revises: 0003_add_saved_job_table
Create Date: 2026-06-24 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0005_email_verification'
down_revision = '0003_add_saved_job_table'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_cols = [c['name'] for c in insp.get_columns('users')] if 'users' in insp.get_table_names() else []
    existing_uqs = [c['name'] for c in insp.get_unique_constraints('users')] if 'users' in insp.get_table_names() else []

    with op.batch_alter_table('users') as batch_op:
        if 'email_verified' not in existing_cols:
            batch_op.add_column(sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'))
        if 'verification_token' not in existing_cols:
            batch_op.add_column(sa.Column('verification_token', sa.String(), nullable=True))
            batch_op.create_unique_constraint('uq_users_verification_token', ['verification_token'])
        elif 'uq_users_verification_token' not in existing_uqs:
            pass
        if 'verification_token_expiry' not in existing_cols:
            batch_op.add_column(sa.Column('verification_token_expiry', sa.DateTime(timezone=True), nullable=True))
        if 'reset_password_token' not in existing_cols:
            batch_op.add_column(sa.Column('reset_password_token', sa.String(), nullable=True))
            batch_op.create_unique_constraint('uq_users_reset_password_token', ['reset_password_token'])
        if 'reset_password_token_expiry' not in existing_cols:
            batch_op.add_column(sa.Column('reset_password_token_expiry', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_cols = [c['name'] for c in insp.get_columns('users')] if 'users' in insp.get_table_names() else []
    existing_uqs = [c['name'] for c in insp.get_unique_constraints('users')] if 'users' in insp.get_table_names() else []

    with op.batch_alter_table('users') as batch_op:
        if 'uq_users_reset_password_token' in existing_uqs:
            batch_op.drop_constraint('uq_users_reset_password_token', type_='unique')
        if 'reset_password_token_expiry' in existing_cols:
            batch_op.drop_column('reset_password_token_expiry')
        if 'reset_password_token' in existing_cols:
            batch_op.drop_column('reset_password_token')
        if 'uq_users_verification_token' in existing_uqs:
            batch_op.drop_constraint('uq_users_verification_token', type_='unique')
        if 'verification_token_expiry' in existing_cols:
            batch_op.drop_column('verification_token_expiry')
        if 'verification_token' in existing_cols:
            batch_op.drop_column('verification_token')
        if 'email_verified' in existing_cols:
            batch_op.drop_column('email_verified')

