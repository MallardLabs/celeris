from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Enum, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum
from datetime import datetime

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
    
    organization = relationship("Organization", back_populates="payment_schedules")