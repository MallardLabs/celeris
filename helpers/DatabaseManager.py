from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.database import Base

class DatabaseManager:
    _instance = None

    def __init__(self, db_url):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    @classmethod
    def get_instance(cls, db_url=None):
        if cls._instance is None and db_url is not None:
            cls._instance = cls(db_url)
        return cls._instance

    def get_session(self):
        return self.Session() 