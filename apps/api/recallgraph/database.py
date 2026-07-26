from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from recallgraph.config import Settings


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, settings: Settings) -> None:
        engine_options: dict[str, object] = {"pool_pre_ping": True}
        if settings.database_url.startswith("sqlite"):
            self._prepare_sqlite_path(settings.database_url)
            engine_options["connect_args"] = {"check_same_thread": False}
            if settings.database_url in {"sqlite://", "sqlite:///:memory:"}:
                engine_options["poolclass"] = StaticPool

        self.engine = create_engine(settings.database_url, **engine_options)
        if settings.database_url.startswith("sqlite"):
            self._enable_sqlite_foreign_keys(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
        )

    @staticmethod
    def _prepare_sqlite_path(database_url: str) -> None:
        database_name = make_url(database_url).database
        if not database_name or database_name == ":memory:":
            return
        parent = Path(database_name).expanduser().parent
        if parent != Path("."):
            parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _enable_sqlite_foreign_keys(engine: Engine) -> None:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    def create_schema(self) -> None:
        # Importing registers every model on Base.metadata.
        from recallgraph.memory import models

        _ = models
        Base.metadata.create_all(self.engine)

    def check(self) -> None:
        with self.session_factory() as session:
            session.execute(text("SELECT 1"))

    def dispose(self) -> None:
        self.engine.dispose()


def get_db(request: Request) -> Generator[Session, None, None]:
    database: Database = request.app.state.database
    session = database.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_db)]
