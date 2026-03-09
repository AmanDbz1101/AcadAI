"""
Database module for persisting Docling-extracted document data.

Provides:
- SQLAlchemy ORM models (models.py)
- Database connection management (connection.py)
- Repository pattern for CRUD operations (repository.py)
- Ingestion pipeline that populates the DB (ingestion_pipeline.py)
"""

from backend.database.connection import DatabaseConnection, get_db_session
from backend.database.models import (
    DocumentRecord,
    SectionRecord,
    TextBlockRecord,
    TableRecord,
    FigureRecord,
    FormulaRecord,
)
from backend.database.repository import DocumentRepository

__all__ = [
    "DatabaseConnection",
    "get_db_session",
    "DocumentRecord",
    "SectionRecord",
    "TextBlockRecord",
    "TableRecord",
    "FigureRecord",
    "FormulaRecord",
    "DocumentRepository",
]
