"""Declarative base for this server's own tables. Deliberately separate from the a2a-sdk's
`a2a.server.models.Base` (which owns `a2a_tasks`) so the two MetaData registries on the one
shared engine can't collide. Alembic owns the DDL; this base is never used for create_all."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
