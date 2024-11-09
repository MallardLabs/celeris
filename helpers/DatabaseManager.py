from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.database import Base
import os
from sqlalchemy import text

class DatabaseManager:
    _instance = None

    def __init__(self, db_url):
        self.db_url = db_url
        self.engine = None
        self.Session = None
        self.initialize_database()

    def initialize_database(self):
        if self.db_url.startswith('sqlite:///'):
            db_file = self.db_url[10:]
            db_dir = os.path.dirname(db_file)
            
            # Create directory if it doesn't exist
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, mode=0o755)
            
            # Remove existing database if it's readonly
            if os.path.exists(db_file):
                try:
                    # Test write permissions
                    with open(db_file, 'a'):
                        pass
                except PermissionError:
                    os.chmod(db_file, 0o666)  # Set read/write permissions
                    if os.path.exists(db_file):
                        os.remove(db_file)
        
        # Create engine with proper permissions
        self.engine = create_engine(
            self.db_url,
            connect_args={'check_same_thread': False},
            echo=True  # Enable SQL logging
        )
        
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        # Verify write permissions by testing a simple write
        try:
            session = self.Session()
            session.execute(text("SELECT 1"))
            session.commit()
        except Exception as e:
            print(f"Database write test failed: {e}")
            raise
        finally:
            session.close()

    @classmethod
    def get_instance(cls, db_url=None):
        if cls._instance is None and db_url is not None:
            cls._instance = cls(db_url)
        return cls._instance

    def reset_database(self):
        """Reset the database completely"""
        if self.db_url.startswith('sqlite:///'):
            db_file = self.db_url[10:]
            if os.path.exists(db_file):
                os.chmod(db_file, 0o666)  # Ensure write permissions
                os.remove(db_file)
        
        Base.metadata.create_all(self.engine)