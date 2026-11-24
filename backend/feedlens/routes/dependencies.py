"""Database dependency for handlers and router factories."""
from __future__ import annotations


from feedlens.db.repository import Database


def db() -> Database:
    from feedlens.api import app
    return app.state.db
