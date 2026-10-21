"""Engine and session factory.

Callers own the transaction. Import functions flush and do not commit.
"""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(database_url: str) -> Engine:
    """Open a PostgreSQL engine. The URL comes from settings or a test fixture."""
    return create_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory that keeps loaded attributes after commit."""
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=True)
