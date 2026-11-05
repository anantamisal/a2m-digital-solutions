"""
Database configuration and models for A2M Digital Solutions
"""
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine, func, Date
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
    timeline = Column(String(50), nullable=True)
    message = Column(Text, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    status = Column(String(20), default="new", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Inquiry(id={self.id}, name='{self.name}', email='{self.email}', service='{self.service}')>"


class VisitorCount(Base):
    """Visitor count tracking"""
    __tablename__ = "visitor_counts"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, nullable=False, index=True)
    count = Column(Integer, default=0, nullable=False)
    unique_visitors = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<VisitorCount(date='{self.date}', count={self.count})>"


class AdminUser(Base):
    """Admin user for dashboard access"""
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<AdminUser(username='{self.username}')>"


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


# CRUD Operations for Inquiries
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


# Visitor Count Operations
def increment_visitor_count(db: Session, is_unique: bool = False) -> VisitorCount:
    """Increment today's visitor count"""
    today = date.today()
    visitor_count = db.query(VisitorCount).filter(VisitorCount.date == today).first()

    if not visitor_count:
        visitor_count = VisitorCount(date=today, count=0, unique_visitors=0)
        db.add(visitor_count)

    visitor_count.count += 1
    if is_unique:
        visitor_count.unique_visitors += 1
    visitor_count.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(visitor_count)
    return visitor_count


def get_visitor_stats(db: Session) -> dict:
    """Get visitor statistics"""
    total_visits = db.query(func.sum(VisitorCount.count)).scalar() or 0
    today = date.today()
    today_count = db.query(VisitorCount).filter(VisitorCount.date == today).first()
    today_visits = today_count.count if today_count else 0
    unique_visitors = db.query(func.sum(VisitorCount.unique_visitors)).scalar() or 0
    return {
        "total_visits": total_visits,
        "today_visits": today_visits,
        "unique_visitors": unique_visitors
    }


# Admin User Operations
def get_admin_user(db: Session, username: str):
    """Get admin user by username"""
    return db.query(AdminUser).filter(AdminUser.username == username).first()


def create_admin_user(db: Session, username: str, password_hash: str) -> AdminUser:
    """Create admin user"""
    admin = AdminUser(username=username, password_hash=password_hash)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def update_last_login(db: Session, admin_id: int):
    """Update admin last login"""
    admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if admin:
        admin.last_login = datetime.utcnow()
        db.commit()
        db.refresh(admin)
    return admin