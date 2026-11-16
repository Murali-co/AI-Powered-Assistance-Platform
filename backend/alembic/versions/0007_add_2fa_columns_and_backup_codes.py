"""Add 2FA columns to users and two_factor_backup_codes table

Revision ID: 0007_2fa_and_backup_codes
Revises: 0006_refresh_tokens_and_audit_log
Create Date: 2026-08-17 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0007_2fa_and_backup_codes'
down_revision = '0006_refresh_and_audit_log'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('two_factor_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('two_factor_secret', sa.String(), nullable=True))

    op.create_table(
        'two_factor_backup_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_two_factor_backup_codes_id'), 'two_factor_backup_codes', ['id'], unique=False)
    op.create_index(op.f('ix_two_factor_backup_codes_user_id'), 'two_factor_backup_codes', ['user_id'], unique=False)
    op.create_index(op.f('ix_two_factor_backup_codes_code_hash'), 'two_factor_backup_codes', ['code_hash'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_two_factor_backup_codes_code_hash'), table_name='two_factor_backup_codes')
    op.drop_index(op.f('ix_two_factor_backup_codes_user_id'), table_name='two_factor_backup_codes')
    op.drop_index(op.f('ix_two_factor_backup_codes_id'), table_name='two_factor_backup_codes')
    op.drop_table('two_factor_backup_codes')

    op.drop_column('users', 'two_factor_secret')
    op.drop_column('users', 'two_factor_enabled')
