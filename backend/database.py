"""
Database configuration and models for A2M Digital Solutions
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from config import get_settings

settings = get_settings()

# SQLAlchemy setup
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}  # Needed for SQLite
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class Inquiry(Base):
    """Inquiry model for storing client inquiries"""
    __tablename__ = "inquiries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(50), nullable=True)
    service = Column(String(100), nullable=False)
    budget = Column(String(50), nullable=True)
    timeline = Column(String(50), nullable=True)
    message = Column(Text, nullable=False)
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(Text, nullable=True)
    status = Column(String(20), default="new", nullable=False)  # new, contacted, closed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Inquiry(id={self.id}, name='{self.name}', email='{self.email}', service='{self.service}')>"


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Dependency for getting DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# CRUD Operations
def create_inquiry(db: Session, inquiry_data: dict) -> Inquiry:
    """Create a new inquiry"""
    inquiry = Inquiry(**inquiry_data)
    db.add(inquiry)
    db.commit()
    db.refresh(inquiry)
    return inquiry


def get_inquiries(db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None):
    """Get inquiries with optional filtering"""
    query = db.query(Inquiry)
    if status:
        query = query.filter(Inquiry.status == status)
    return query.order_by(Inquiry.created_at.desc()).offset(skip).limit(limit).all()


def get_inquiry(db: Session, inquiry_id: int) -> Optional[Inquiry]:
    """Get a single inquiry by ID"""
    return db.query(Inquiry).filter(Inquiry.id == inquiry_id).first()


def update_inquiry_status(db: Session, inquiry_id: int, status: str) -> Optional[Inquiry]:
    """Update inquiry status"""
    inquiry = db.query(Inquiry).filter(Inquiry.id == inquiry_id).first()
    if inquiry:
        inquiry.status = status
        inquiry.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(inquiry)
    return inquiry


def get_inquiry_stats(db: Session) -> dict:
    """Get inquiry statistics"""
    total = db.query(Inquiry).count()
    new = db.query(Inquiry).filter(Inquiry.status == "new").count()
    contacted = db.query(Inquiry).filter(Inquiry.status == "contacted").count()
    closed = db.query(Inquiry).filter(Inquiry.status == "closed").count()
    return {
        "total": total,
        "new": new,
        "contacted": contacted,
        "closed": closed
    }