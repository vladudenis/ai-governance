"""Request dependencies."""

from collections.abc import Iterator

from fastapi import Header, Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    """Yield a session and commit when the route returns."""
    session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_actor(x_actor: str | None = Header(default=None, alias="X-Actor")) -> str:
    """Name recorded on audit events. An empty header stays unspecified."""
    if x_actor and x_actor.strip():
        return x_actor.strip()[:200]
    return "unspecified"
