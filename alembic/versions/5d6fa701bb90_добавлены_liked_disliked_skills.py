"""Добавлены liked, disliked, skills

Revision ID: 5d6fa701bb90
Revises: a61e4168aa5c
Create Date: 2026-07-12 13:47:50.244270
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '5d6fa701bb90'
down_revision = 'a61e4168aa5c'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Добавляем колонки в таблицу users, если их ещё нет
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'skills' not in columns:
        op.add_column('users', sa.Column('skills', sa.JSON(), nullable=True, server_default='[]'))
    if 'liked' not in columns:
        op.add_column('users', sa.Column('liked', sa.JSON(), nullable=True, server_default='[]'))
    if 'disliked' not in columns:
        op.add_column('users', sa.Column('disliked', sa.JSON(), nullable=True, server_default='[]'))

    # 2. Пересоздаём таблицу vacancy_actions с правильным внешним ключом на users.tg_id
    #    recreate='always' заставляет Alembic создать новую таблицу, скопировать данные и заменить старую
    with op.batch_alter_table('vacancy_actions', recreate='always') as batch_op:
        batch_op.create_foreign_key(
            'fk_vacancy_actions_user_id',  # задаём явное имя
            'users',                       # ссылаемся на таблицу users
            ['user_id'],                   # колонка в текущей таблице
            ['tg_id'],                     # колонка в users
            ondelete='CASCADE'
        )

def downgrade():
    # Откат: удаляем колонки
    op.drop_column('users', 'disliked')
    op.drop_column('users', 'liked')
    op.drop_column('users', 'skills')
    
    # Возвращаем внешний ключ обратно на users.id
    with op.batch_alter_table('vacancy_actions', recreate='always') as batch_op:
        batch_op.create_foreign_key(
            None,        # автоматическое имя
            'users',
            ['user_id'],
            ['id'],
            ondelete='CASCADE'
        )