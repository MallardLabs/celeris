from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Enum, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
from sqlalchemy.orm import sessionmaker
from models.database import Base
import os

Base = declarative_base()

class IntervalType(enum.Enum):
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"

class Organization(Base):
    __tablename__ = 'organizations'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    owner_id = Column(String)  # Discord user ID
    created_at = Column(DateTime, default=datetime.utcnow)
    
    members = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    payment_schedules = relationship("PaymentSchedule", back_populates="organization", cascade="all, delete-orphan")

class OrganizationMember(Base):
    __tablename__ = 'organization_members'
    
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'))
    user_id = Column(String)  # Discord user ID
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    organization = relationship("Organization", back_populates="members")
class PaymentSchedule(Base):
    __tablename__ = 'payment_schedules'
    
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'))
    user_id = Column(String, nullable=True)  # Discord user ID, null if org-wide
    amount = Column(Integer)
    interval_type = Column(Enum(IntervalType))
    interval_value = Column(Integer)
    last_paid_at = Column(DateTime, default=datetime.utcnow)
    total_points = Column(Integer)  # Total points allocated to this schedule
    points_paid = Column(Integer, default=0)  # Points already paid out

class DatabaseManager:
    _instance = None

    def __init__(self, db_url):
        # Extract filename from SQLite URL (e.g., "sqlite:///your_database.db" -> "your_database.db")
        if db_url.startswith('sqlite:///'):
            db_file = db_url[10:]
            # Delete existing database file if it exists
            if os.path.exists(db_file):
                os.remove(db_file)
                
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

    def reset_database(self):
        """Reset the database - USE WITH CAUTION"""
        # Extract filename from SQLite URL
        if str(self.engine.url).startswith('sqlite:///'):
            db_file = str(self.engine.url)[10:]
            # Delete existing database file if it exists
            if os.path.exists(db_file):
                os.remove(db_file)
        
        Base.metadata.create_all(self.engine)