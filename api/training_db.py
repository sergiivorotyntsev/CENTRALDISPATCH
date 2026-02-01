"""SQLModel database setup for training system.

This module provides SQLModel/SQLAlchemy session management for the training
system, separate from the main SQLite-based database.py module.
"""
from pathlib import Path
from typing import Generator

from sqlmodel import SQLModel, Session, create_engine

# Training database path (separate from main control_panel.db for modularity)
TRAINING_DB_PATH = Path(__file__).parent.parent / "data" / "training.db"

# Ensure data directory exists
TRAINING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# SQLModel engine
engine = create_engine(
    f"sqlite:///{TRAINING_DB_PATH}",
    echo=False,  # Set to True for SQL debugging
    connect_args={"check_same_thread": False}  # Allow multi-thread access
)


def init_training_db():
    """Initialize training database tables."""
    from models.training import (
        ExtractionRule,
        FieldCorrection,
        TrainingExample,
        ExtractionPattern,
    )
    SQLModel.metadata.create_all(engine, tables=[
        ExtractionRule.__table__,
        FieldCorrection.__table__,
        TrainingExample.__table__,
        ExtractionPattern.__table__,
    ])


def get_session() -> Generator[Session, None, None]:
    """Get a SQLModel session for dependency injection."""
    with Session(engine) as session:
        yield session
