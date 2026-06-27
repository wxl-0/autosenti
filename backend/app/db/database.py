from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.db import models  # noqa

    Base.metadata.create_all(bind=engine)
    ensure_sqlite_columns()


def ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    conversation_tables = [
        "uploaded_files",
        "data_sources",
        "feedback_items",
        "metric_snapshots",
        "document_chunks",
        "insight_clusters",
        "opportunities",
        "prd_documents",
        "agent_runs",
        "project_memory",
    ]
    with engine.begin() as conn:
        inspector = inspect(conn)
        for table in conversation_tables:
            if table not in inspector.get_table_names():
                continue
            columns = {col["name"] for col in inspector.get_columns(table)}
            if "conversation_id" not in columns:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN conversation_id VARCHAR(80)"))
        # agent_runs: report_markdown column added in AutoSenti
        if "agent_runs" in inspector.get_table_names():
            cols = {col["name"] for col in inspector.get_columns("agent_runs")}
            if "report_markdown" not in cols:
                conn.execute(text("ALTER TABLE agent_runs ADD COLUMN report_markdown TEXT"))
