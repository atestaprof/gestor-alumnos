import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "gestor.db"


def _database_url() -> str:
    """DATABASE_URL (p. ej. PostgreSQL en Render) o SQLite local como respaldo."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        DB_PATH.parent.mkdir(exist_ok=True)
        return f"sqlite:///{DB_PATH}"
    # Render/Heroku entregan "postgres://"; SQLAlchemy requiere el driver explícito (psycopg 3).
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    **({"connect_args": {"check_same_thread": False}} if IS_SQLITE else {"pool_pre_ping": True}),
)

if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate():
    """Migra bases existentes: agrega pct_practicas (con 0 para no alterar sumas previas)
    y reconstruye la tabla para actualizar la restricción de suma = 100."""
    from sqlalchemy import text, inspect
    if not IS_SQLITE:  # en bases nuevas (PostgreSQL) create_all ya crea el esquema completo
        return
    insp = inspect(engine)
    if "criterios_evaluacion" not in insp.get_table_names():
        return
    if "pct_practicas" in {c["name"] for c in insp.get_columns("criterios_evaluacion")}:
        return
    with engine.begin() as cx:
        cx.execute(text("ALTER TABLE criterios_evaluacion RENAME TO criterios_old"))
        Base.metadata.tables["criterios_evaluacion"].create(cx)
        cx.execute(text(
            "INSERT INTO criterios_evaluacion (id, grupo_id, pct_asistencia, pct_tareas, pct_practicas, pct_examenes) "
            "SELECT id, grupo_id, pct_asistencia, pct_tareas, 0, pct_examenes FROM criterios_old"))
        cx.execute(text("DROP TABLE criterios_old"))
