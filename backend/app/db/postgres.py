from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker , declarative_base
from app.setting import settings

db_url=settings.DATABASE_URL

engine =create_engine(db_url)

sessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

base = declarative_base()

def get_db():
    db=sessionLocal()
    try:
        print("db connection request by get_db")
        yield db
    finally: 
        print("db connection fail")
        db.close()
