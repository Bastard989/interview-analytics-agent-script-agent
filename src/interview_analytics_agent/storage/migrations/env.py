"""
Alembic env.py (миграции БД).

Назначение:
- подключить metadata моделей
- дать Alembic доступ к DATABASE URL

Важно:
- В dev можно использовать POSTGRES_DSN из ENV
- Alembic ожидает sqlalchemy.url, но мы подставляем его программно
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.storage.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = get_settings()
    url = settings.postgres_dsn.replace("+psycopg", "")  # alembic лучше с чистым driver
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = get_settings()
    url = settings.postgres_dsn.replace("+psycopg", "")

    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
