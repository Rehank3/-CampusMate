from datetime import datetime
from pathlib import Path
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

# Store SQLite database file in the backend directory
DB_PATH = Path(__file__).resolve().parent / "campusmate.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# Uploads folder — sibling to the database file
UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class AssignmentDB(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    subject = Column(String(100), nullable=False)
    deadline = Column(String(50), nullable=False)
    priority = Column(String(20), default="Medium", nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Attachment metadata (nullable — only present when a file was uploaded)
    attachment_original_name = Column(String(300), nullable=True)
    attachment_stored_name = Column(String(300), nullable=True)
    attachment_mime_type = Column(String(100), nullable=True)
    extracted_text = Column(Text, nullable=True)

    @property
    def days_remaining(self) -> int:
        """Returns the difference in days between the deadline and today."""
        try:
            deadline_date = datetime.strptime(self.deadline, "%Y-%m-%d").date()
            return (deadline_date - datetime.now().date()).days
        except (ValueError, TypeError):
            return 999

    @property
    def urgency(self) -> str:
        """Calculates urgency status: Overdue, Due Today, Due Soon, or Upcoming."""
        if self.is_completed:
            return "Completed"
        days = self.days_remaining
        if days < 0:
            return "Overdue"
        elif days == 0:
            return "Due Today"
        elif 1 <= days <= 3:
            return "Due Soon"
        else:
            return "Upcoming"


def init_db():
    """Create database tables if they do not exist."""
    Base.metadata.create_all(bind=engine)


def migrate_db():
    """
    Safe, additive migration: add new columns to the existing 'assignments'
    table if they are not already present.  Never drops data.
    """
    new_columns = [
        ("attachment_original_name", "TEXT"),
        ("attachment_stored_name",   "TEXT"),
        ("attachment_mime_type",     "TEXT"),
        ("extracted_text",           "TEXT"),
    ]
    with engine.connect() as conn:
        for col_name, col_type in new_columns:
            try:
                conn.execute(
                    text(f"ALTER TABLE assignments ADD COLUMN {col_name} {col_type}")
                )
                conn.commit()
            except Exception:
                # Column already exists — ignore
                pass


def get_db():
    """Dependency for obtaining a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
