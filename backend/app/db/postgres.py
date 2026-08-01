from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.setting import settings

db_url = settings.DATABASE_URL

engine = create_engine(db_url)

sessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

base = Base


def get_db():
    db = sessionLocal()
    try:
        yield db
    finally:
        db.close()
