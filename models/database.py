from datetime import datetime
import enum
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, create_engine
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class IntervalType(enum.Enum):
    SECONDS = "s"
    MINUTES = "m"
    HOURS = "h"
    DAYS = "d"
    MONTHS = "mm"

class Organization(Base):
    __tablename__ = 'organizations'
    
    id = Column(Integer, primary_key=True)
    name = Column(String)
    owner_id = Column(String)  # Discord user ID
    created_at = Column(DateTime, default=datetime.utcnow)
    
    members = relationship("OrganizationMember", back_populates="organization")
    payment_schedules = relationship("PaymentSchedule", back_populates="organization")

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
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=True)
    user_id = Column(String, nullable=True)  # Discord user ID for individual schedules
    amount = Column(Integer)
    interval_type = Column(Enum(IntervalType))
    interval_value = Column(Integer)
    last_paid_at = Column(DateTime, default=datetime.utcnow)
    total_points = Column(Integer)
    points_paid = Column(Integer, default=0)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    organization = relationship("Organization", back_populates="payment_schedules")
    members = relationship("PaymentScheduleMember", back_populates="schedule")

class PaymentScheduleMember(Base):
    __tablename__ = 'payment_schedule_members'
    
    id = Column(Integer, primary_key=True)
    schedule_id = Column(Integer, ForeignKey('payment_schedules.id'))
    user_id = Column(String)  # Discord user ID
    created_at = Column(DateTime, default=datetime.utcnow)

    schedule = relationship("PaymentSchedule", back_populates="members")