"""
Инициализация базы данных и сессий SQLAlchemy.

Назначение:
- Создание engine
- Контекстный менеджер для сессий
- Единая точка доступа к БД для всех сервисов
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from interview_analytics_agent.common.config import get_settings

# =============================================================================
# ENGINE / SESSION FACTORY
# =============================================================================
_settings = get_settings()

engine = create_engine(
    _settings.postgres_dsn,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# =============================================================================
# CONTEXT MANAGER
# =============================================================================
@contextmanager
def db_session() -> Session:
    """
    Контекстный менеджер для работы с БД.

    Использование:
        with db_session() as session:
            session.add(...)
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
