import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

db_url = settings.DATABASE_URL
# If URL is postgresql:// and psycopg2 is installed, map to postgresql+psycopg2://
if db_url.startswith("postgresql://"):
    db_url = "postgresql+psycopg2://" + db_url[len("postgresql://"):]

engine_kwargs = {"pool_pre_ping": True}
if "sqlite" in db_url:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

try:
    engine = create_engine(db_url, **engine_kwargs)
    with engine.connect() as conn:
        pass
except Exception as e:
    import os
    from sqlalchemy.engine.url import make_url
    db_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dev.db"))
    try:
        safe_db_url = make_url(db_url).render_as_string(hide_password=True)
    except Exception:
        safe_db_url = "[unparseable database url]"
    logger.warning(f"Database connection to {safe_db_url} failed ({e}). Falling back to local SQLite: sqlite:///{db_file}")
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()



def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
