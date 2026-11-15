"""Add last_totp_step to users table

Revision ID: 0013_add_last_totp_step
Revises: 0012_auth_refresh_and_lockout
Create Date: 2026-10-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0013_add_last_totp_step'
down_revision = '0012_auth_refresh_and_lockout'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'users' in tables:
        existing_user_cols = [c['name'] for c in insp.get_columns('users')]
        if 'last_totp_step' not in existing_user_cols:
            with op.batch_alter_table('users') as batch_op:
                batch_op.add_column(
                    sa.Column('last_totp_step', sa.Integer(), nullable=True)
                )

        # Ensure required index is created independently of whether the column was newly added
        existing_user_indexes = [idx['name'] for idx in insp.get_indexes('users')]
        if 'ix_users_last_totp_step' not in existing_user_indexes:
            op.create_index(
                op.f('ix_users_last_totp_step'),
                'users',
                ['last_totp_step'],
                unique=False
            )

    if 'auth_audit_log' in tables:
        existing_audit_indexes = [idx['name'] for idx in insp.get_indexes('auth_audit_log')]
        if 'ix_auth_audit_log_event_email_created' not in existing_audit_indexes:
            op.create_index(
                'ix_auth_audit_log_event_email_created',
                'auth_audit_log',
                ['event_type', 'email', 'created_at'],
                unique=False
            )
        if 'ix_auth_audit_log_event_ip_created' not in existing_audit_indexes:
            op.create_index(
                'ix_auth_audit_log_event_ip_created',
                'auth_audit_log',
                ['event_type', 'ip_address', 'created_at'],
                unique=False
            )


def downgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'auth_audit_log' in tables:
        existing_audit_indexes = [idx['name'] for idx in insp.get_indexes('auth_audit_log')]
        if 'ix_auth_audit_log_event_ip_created' in existing_audit_indexes:
            op.drop_index('ix_auth_audit_log_event_ip_created', table_name='auth_audit_log')
        if 'ix_auth_audit_log_event_email_created' in existing_audit_indexes:
            op.drop_index('ix_auth_audit_log_event_email_created', table_name='auth_audit_log')

    if 'users' in tables:
        existing_user_indexes = [idx['name'] for idx in insp.get_indexes('users')]
        if 'ix_users_last_totp_step' in existing_user_indexes:
            op.drop_index(op.f('ix_users_last_totp_step'), table_name='users')

        existing_user_cols = [c['name'] for c in insp.get_columns('users')]
        if 'last_totp_step' in existing_user_cols:
            with op.batch_alter_table('users') as batch_op:
                batch_op.drop_column('last_totp_step')
