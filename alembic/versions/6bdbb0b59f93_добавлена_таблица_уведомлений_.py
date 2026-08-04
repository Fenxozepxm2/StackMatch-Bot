"""добавлена таблица уведомлений пользователя

Revision ID: 6bdbb0b59f93
Revises: 5d6fa701bb90
Create Date: 2026-08-07 14:16:05.703676

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '6bdbb0b59f93'
down_revision = '5d6fa701bb90'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Добавляем колонку, если её нет
    columns = [col['name'] for col in inspector.get_columns('users')]
    if 'last_vacancy_check' not in columns:
        op.add_column('users', sa.Column('last_vacancy_check', sa.DateTime(timezone=True), nullable=True))
    
    # Создаём таблицу, если её нет
    tables = inspector.get_table_names()
    if 'users_notification' not in tables:
        op.create_table(
            'users_notification',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tg_id', sa.Integer(), nullable=False),
            sa.Column('vacancy_id', sa.String(length=124), nullable=False),
            sa.Column('vacancy_data', sa.JSON(), nullable=True, server_default='[]'),
            sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('viewed', sa.Boolean(), nullable=False, server_default='False'),
            sa.ForeignKeyConstraint(['tg_id'], ['users.tg_id'], ondelete='CASCADE', name='fk_user_notification_tg_id'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_users_notification_tg_id', 'users_notification', ['tg_id'], unique=False)


def downgrade():
    op.drop_table('users_notification')
    op.drop_column('users', 'last_vacancy_check')