"""Repair auth_audit_log schema for login lockout tracking.

Revision ID: 0014_auth_audit_lockout_repair
Revises: 0013_add_last_totp_step
Create Date: 2026-10-25 00:00:00.000000

This repair migration is intentionally idempotent: it adds the nullable
``email`` column when missing and creates the lockout/audit indexes whenever
missing, without attempting to recreate existing schema objects.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0014_auth_audit_lockout_repair'
down_revision = '0013_add_last_totp_step'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'refresh_tokens' in tables:
        existing_rt_cols = [c['name'] for c in insp.get_columns('refresh_tokens')]
        if 'replaced_by' not in existing_rt_cols:
            op.add_column(
                'refresh_tokens',
                sa.Column('replaced_by', sa.String(length=64), nullable=True)
            )
        if 'auth_time' not in existing_rt_cols:
            op.add_column(
                'refresh_tokens',
                sa.Column('auth_time', sa.Integer(), nullable=True)
            )

        existing_rt_indexes = [idx['name'] for idx in insp.get_indexes('refresh_tokens')]
        if 'ix_refresh_tokens_replaced_by' not in existing_rt_indexes:
            op.create_index(
                op.f('ix_refresh_tokens_replaced_by'),
                'refresh_tokens',
                ['replaced_by'],
                unique=False
            )

    if 'auth_audit_log' in tables:
        existing_audit_cols = [c['name'] for c in insp.get_columns('auth_audit_log')]
        if 'email' not in existing_audit_cols:
            op.add_column(
                'auth_audit_log',
                sa.Column('email', sa.String(length=255), nullable=True)
            )

        existing_audit_indexes = [idx['name'] for idx in insp.get_indexes('auth_audit_log')]

        if 'ix_auth_audit_log_email' not in existing_audit_indexes:
            op.create_index(
                op.f('ix_auth_audit_log_email'),
                'auth_audit_log',
                ['email'],
                unique=False
            )

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

    if 'refresh_tokens' in tables:
        existing_rt_indexes = [idx['name'] for idx in insp.get_indexes('refresh_tokens')]
        if 'ix_refresh_tokens_replaced_by' in existing_rt_indexes:
            op.drop_index(op.f('ix_refresh_tokens_replaced_by'), table_name='refresh_tokens')

        existing_rt_cols = [c['name'] for c in insp.get_columns('refresh_tokens')]
        if 'auth_time' in existing_rt_cols:
            op.drop_column('refresh_tokens', 'auth_time')
        if 'replaced_by' in existing_rt_cols:
            op.drop_column('refresh_tokens', 'replaced_by')

    if 'auth_audit_log' in tables:
        existing_audit_indexes = [idx['name'] for idx in insp.get_indexes('auth_audit_log')]

        if 'ix_auth_audit_log_event_ip_created' in existing_audit_indexes:
            op.drop_index('ix_auth_audit_log_event_ip_created', table_name='auth_audit_log')
        if 'ix_auth_audit_log_event_email_created' in existing_audit_indexes:
            op.drop_index('ix_auth_audit_log_event_email_created', table_name='auth_audit_log')
        if 'ix_auth_audit_log_email' in existing_audit_indexes:
            op.drop_index(op.f('ix_auth_audit_log_email'), table_name='auth_audit_log')

        existing_audit_cols = [c['name'] for c in insp.get_columns('auth_audit_log')]
        if 'email' in existing_audit_cols:
            op.drop_column('auth_audit_log', 'email')
