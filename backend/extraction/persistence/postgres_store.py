"""
PostgreSQL persistence for extracted paper artifacts.

Stores one paper record per unique paper name (case-insensitive), and links
sections, text blocks, tables, and images to that paper for later retrieval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class PaperRecord(Base):
    __tablename__ = "papers"
    __table_args__ = (
        Index("uq_papers_name_lower", func.lower(text("paper_name")), unique=True),
        Index("uq_papers_pdf_hash", "pdf_hash", unique=True, postgresql_where=text("pdf_hash IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_name: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    pdf_hash: Mapped[Optional[str]] = mapped_column(Text)
    source_pdf_path: Mapped[Optional[str]] = mapped_column(Text)
    document_uuid: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sections: Mapped[list["SectionRecord"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    text_blocks: Mapped[list["TextBlockRecord"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    tables: Mapped[list["TableDataRecord"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    images: Mapped[list["ImageRecord"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    references: Mapped[list["ReferenceRecord"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    user_links: Mapped[list["UserPaperRecord"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    guides: Mapped[list["PaperGuideRecord"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    questions: Mapped[list["PaperQuestionRecord"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


class UserRecord(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_email_lower", func.lower(text("email")), unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_salt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    paper_links: Mapped[list["UserPaperRecord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SectionRecord(Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("paper_id", "section_key", name="uq_sections_paper_section_key"),
        Index("idx_sections_paper_id", "paper_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    section_key: Mapped[str] = mapped_column(Text, nullable=False)
    parent_section_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("sections.id", ondelete="SET NULL")
    )
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    stats_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    paper: Mapped[PaperRecord] = relationship(back_populates="sections")


class TextBlockRecord(Base):
    __tablename__ = "text_blocks"
    __table_args__ = (
        UniqueConstraint("paper_id", "element_id", name="uq_text_blocks_paper_element"),
        Index("idx_text_blocks_paper_id", "paper_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    element_id: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    text_content: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    paper: Mapped[PaperRecord] = relationship(back_populates="text_blocks")


class TableDataRecord(Base):
    __tablename__ = "tables_data"
    __table_args__ = (
        UniqueConstraint("paper_id", "element_id", name="uq_tables_data_paper_element"),
        Index("idx_tables_data_paper_id", "paper_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    element_id: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    markdown_content: Mapped[Optional[str]] = mapped_column(Text)
    text_content: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    paper: Mapped[PaperRecord] = relationship(back_populates="tables")


class ImageRecord(Base):
    __tablename__ = "images"
    __table_args__ = (
        UniqueConstraint("paper_id", "element_id", name="uq_images_paper_element"),
        Index("idx_images_paper_id", "paper_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    element_id: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    image_path: Mapped[Optional[str]] = mapped_column(Text)
    caption: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    paper: Mapped[PaperRecord] = relationship(back_populates="images")


class ReferenceRecord(Base):
    __tablename__ = "references_data"
    __table_args__ = (
        UniqueConstraint("paper_id", "element_id", name="uq_references_data_paper_element"),
        Index("idx_references_data_paper_id", "paper_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    element_id: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    reference_text: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    paper: Mapped[PaperRecord] = relationship(back_populates="references")


class SectionTextBlockRecord(Base):
    __tablename__ = "section_text_blocks"
    section_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sections.id", ondelete="CASCADE"), primary_key=True
    )
    text_block_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("text_blocks.id", ondelete="CASCADE"), primary_key=True
    )


class SectionTableRecord(Base):
    __tablename__ = "section_tables"
    section_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sections.id", ondelete="CASCADE"), primary_key=True
    )
    table_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tables_data.id", ondelete="CASCADE"), primary_key=True
    )


class SectionImageRecord(Base):
    __tablename__ = "section_images"
    section_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sections.id", ondelete="CASCADE"), primary_key=True
    )
    image_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("images.id", ondelete="CASCADE"), primary_key=True
    )


class UserPaperRecord(Base):
    __tablename__ = "user_papers"
    __table_args__ = (
        UniqueConstraint("user_id", "paper_id", name="uq_user_papers_user_paper"),
        Index("idx_user_papers_user_id", "user_id"),
        Index("idx_user_papers_paper_id", "paper_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[UserRecord] = relationship(back_populates="paper_links")
    paper: Mapped[PaperRecord] = relationship(back_populates="user_links")
class PaperGuideRecord(Base):
    __tablename__ = "paper_guides"
    __table_args__ = (
        UniqueConstraint("paper_id", name="uq_paper_guides_paper_id"),
        Index("idx_paper_guides_paper_id", "paper_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    document_uuid: Mapped[Optional[str]] = mapped_column(Text)
    guide_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    guide_plan_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    guide_file_path: Mapped[Optional[str]] = mapped_column(Text)
    guide_plan_file_path: Mapped[Optional[str]] = mapped_column(Text)
    question_section_pairs_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    paper: Mapped[PaperRecord] = relationship(back_populates="guides")


class PaperQuestionRecord(Base):
    __tablename__ = "paper_questions"
    __table_args__ = (
        Index("idx_paper_questions_paper_id", "paper_id"),
        Index("idx_paper_questions_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    document_uuid: Mapped[Optional[str]] = mapped_column(Text)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    scoped_sections_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    retrieval_payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    answer_text: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    paper: Mapped[PaperRecord] = relationship(back_populates="questions")


@dataclass
class PersistResult:
    """Result from a persistence attempt."""

    stored: bool
    paper_id: Optional[int]
    paper_name: str
    reason: str


class PostgresPaperStore:
    """Persists extraction output into PostgreSQL tables."""

    def __init__(self, dsn: str):
        self.dsn = self._normalize_dsn(dsn)
        self._engine = create_engine(self.dsn, pool_pre_ping=True, future=True)
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)

    @staticmethod
    def _normalize_dsn(dsn: str) -> str:
        if dsn.startswith("postgresql+"):
            return dsn
        if dsn.startswith("postgres://"):
            return dsn.replace("postgres://", "postgresql+psycopg://", 1)
        if dsn.startswith("postgresql://"):
            return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
        return dsn

    @staticmethod
    def _to_dict(record: Any) -> Dict[str, Any]:
        return {column.name: getattr(record, column.name) for column in record.__table__.columns}

    def ensure_schema(self) -> None:
        """Create required tables and indexes if they do not exist."""
        Base.metadata.create_all(self._engine)

    def persist_extraction(
        self,
        *,
        paper_name: str,
        title: Optional[str],
        abstract: Optional[str],
        pdf_hash: Optional[str],
        source_pdf_path: Optional[str],
        document_uuid: Optional[str],
        metadata_json: Dict[str, Any],
        sections: List[Dict[str, Any]],
        extracted_elements: Dict[str, List[Dict[str, Any]]],
    ) -> PersistResult:
        """
        Persist one extraction result if the paper has not been stored yet.

        Deduplication rule:
        - existing `pdf_hash` OR existing case-insensitive `paper_name` => skip.
        """
        paper_name = (paper_name or "").strip()
        if not paper_name:
            return PersistResult(False, None, paper_name, "missing_paper_name")

        self.ensure_schema()
        with self._Session() as session:
            existing_id, reason = self._find_existing_paper(session, paper_name, pdf_hash)
            if existing_id is not None:
                paper_id = int(existing_id)
                references = self._resolve_references(extracted_elements)
                if references:
                    before = (
                        session.query(func.count(ReferenceRecord.id))
                        .filter(ReferenceRecord.paper_id == paper_id)
                        .scalar()
                        or 0
                    )
                    self._insert_references(session, paper_id, references)
                    after = (
                        session.query(func.count(ReferenceRecord.id))
                        .filter(ReferenceRecord.paper_id == paper_id)
                        .scalar()
                        or 0
                    )
                    if after > before:
                        session.commit()
                        return PersistResult(False, paper_id, paper_name, f"{reason}_references_updated")
                return PersistResult(False, paper_id, paper_name, reason)

            paper = PaperRecord(
                paper_name=paper_name,
                title=title,
                abstract=abstract,
                pdf_hash=pdf_hash,
                source_pdf_path=source_pdf_path,
                document_uuid=document_uuid,
                metadata_json=metadata_json or {},
            )
            session.add(paper)
            session.flush()

            paper_id = int(paper.id)
            section_db_map = self._insert_sections(session, paper_id, sections)
            text_map = self._insert_text_blocks(
                session, paper_id, extracted_elements.get("text_blocks", [])
            )
            table_map = self._insert_tables(
                session, paper_id, extracted_elements.get("tables", [])
            )
            image_map = self._insert_images(
                session, paper_id, extracted_elements.get("figures", [])
            )
            references = self._resolve_references(extracted_elements)
            self._insert_references(session, paper_id, references)

            self._link_section_elements(session, section_db_map, text_map, table_map, image_map)
            session.commit()

        return PersistResult(True, paper_id, paper_name, "stored")

    def _resolve_references(self, extracted_elements: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        references = extracted_elements.get("references")
        if not references:
            references = self._extract_references_from_text_blocks(
                extracted_elements.get("text_blocks", [])
            )
        return references or []

    def _find_existing_paper(self, session, paper_name: str, pdf_hash: Optional[str]) -> Tuple[Optional[int], str]:
        if pdf_hash:
            by_hash = session.query(PaperRecord).filter(PaperRecord.pdf_hash == pdf_hash).first()
            if by_hash:
                return int(by_hash.id), "duplicate_pdf_hash"

        by_name = (
            session.query(PaperRecord)
            .filter(func.lower(PaperRecord.paper_name) == paper_name.lower())
            .first()
        )
        if by_name:
            return int(by_name.id), "duplicate_paper_name"

        return None, ""

    def _insert_sections(self, session, paper_id: int, sections: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        section_map: Dict[str, Dict[str, Any]] = {}

        def _walk(nodes: List[Dict[str, Any]], parent_db_id: Optional[int], base_key: str) -> None:
            for idx, section in enumerate(nodes):
                section_key = f"{base_key}.{idx}"
                stats = section.get("stats") or {}

                section_row = SectionRecord(
                    paper_id=paper_id,
                    section_key=section_key,
                    parent_section_id=parent_db_id,
                    original_name=section.get("original_name") or "Untitled",
                    level=int(section.get("level") or 1),
                    page_start=int(section.get("page_start") or 1),
                    position=idx,
                    stats_json=stats,
                )
                session.add(section_row)
                session.flush()
                section_id = int(section_row.id)

                section_map[section_key] = {
                    "id": section_id,
                    "stats": stats,
                }

                children = section.get("sections") or []
                if children:
                    _walk(children, section_id, section_key)

        _walk(sections or [], None, "s")
        return section_map

    def _insert_text_blocks(self, session, paper_id: int, text_blocks: List[Dict[str, Any]]) -> Dict[str, int]:
        mapping: Dict[str, int] = {}
        for block in text_blocks:
            element_id = block.get("id")
            if not element_id:
                continue

            row = (
                session.query(TextBlockRecord)
                .filter(
                    TextBlockRecord.paper_id == paper_id,
                    TextBlockRecord.element_id == element_id,
                )
                .first()
            )
            if row is None:
                row = TextBlockRecord(paper_id=paper_id, element_id=element_id)
                session.add(row)

            row.page_number = block.get("page")
            row.text_content = block.get("text")
            row.metadata_json = block
            session.flush()
            mapping[element_id] = int(row.id)
        return mapping

    def _insert_tables(self, session, paper_id: int, tables: List[Dict[str, Any]]) -> Dict[str, int]:
        mapping: Dict[str, int] = {}
        for table in tables:
            element_id = table.get("id")
            if not element_id:
                continue

            row = (
                session.query(TableDataRecord)
                .filter(
                    TableDataRecord.paper_id == paper_id,
                    TableDataRecord.element_id == element_id,
                )
                .first()
            )
            if row is None:
                row = TableDataRecord(paper_id=paper_id, element_id=element_id)
                session.add(row)

            row.page_number = table.get("page")
            row.markdown_content = table.get("markdown")
            row.text_content = table.get("text")
            row.metadata_json = table
            session.flush()
            mapping[element_id] = int(row.id)
        return mapping

    def _insert_images(self, session, paper_id: int, images: List[Dict[str, Any]]) -> Dict[str, int]:
        mapping: Dict[str, int] = {}
        for image in images:
            element_id = image.get("id")
            if not element_id:
                continue

            row = (
                session.query(ImageRecord)
                .filter(
                    ImageRecord.paper_id == paper_id,
                    ImageRecord.element_id == element_id,
                )
                .first()
            )
            if row is None:
                row = ImageRecord(paper_id=paper_id, element_id=element_id)
                session.add(row)

            row.page_number = image.get("page")
            row.image_path = image.get("image_path")
            row.caption = image.get("caption")
            row.metadata_json = image
            session.flush()
            mapping[element_id] = int(row.id)
        return mapping

    @staticmethod
    def _extract_references_from_text_blocks(text_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        refs: List[Dict[str, Any]] = []
        for block in text_blocks or []:
            label = str(block.get("label") or "").strip().lower()
            section = str(block.get("section_title") or block.get("section") or "").strip().lower()
            text = str(block.get("text") or "").strip()
            is_ref = label in {"reference", "bibliography"} or (
                "reference" in section or "bibliography" in section
            )
            if not is_ref and text:
                if re.match(r"^\s*(references|bibliography|works cited)\b", text, flags=re.I):
                    is_ref = True
            if not is_ref:
                continue

            refs.append(
                {
                    "id": block.get("id"),
                    "page": block.get("page"),
                    "text": text,
                    "label": label,
                    "section_id": block.get("section_id"),
                    "section_title": block.get("section_title"),
                }
            )
        return refs

    def _insert_references(
        self, session, paper_id: int, references: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        mapping: Dict[str, int] = {}
        for idx, ref in enumerate(references or []):
            element_id = ref.get("id") or f"ref_{paper_id}_{idx}"

            row = (
                session.query(ReferenceRecord)
                .filter(
                    ReferenceRecord.paper_id == paper_id,
                    ReferenceRecord.element_id == element_id,
                )
                .first()
            )
            if row is None:
                row = ReferenceRecord(paper_id=paper_id, element_id=element_id)
                session.add(row)

            row.page_number = ref.get("page")
            row.reference_text = ref.get("text")
            row.metadata_json = ref
            session.flush()
            mapping[element_id] = int(row.id)

        return mapping

    def _link_section_elements(
        self,
        session,
        section_db_map: Dict[str, Dict[str, Any]],
        text_map: Dict[str, int],
        table_map: Dict[str, int],
        image_map: Dict[str, int],
    ) -> None:
        for section in section_db_map.values():
            section_id = section["id"]
            stats = section.get("stats") or {}

            for element_id in stats.get("text_block_ids", []):
                text_id = text_map.get(element_id)
                if text_id:
                    link = (
                        session.query(SectionTextBlockRecord)
                        .filter(
                            SectionTextBlockRecord.section_id == section_id,
                            SectionTextBlockRecord.text_block_id == text_id,
                        )
                        .first()
                    )
                    if link is None:
                        session.add(
                            SectionTextBlockRecord(section_id=section_id, text_block_id=text_id)
                        )

            for element_id in stats.get("table_ids", []):
                table_id = table_map.get(element_id)
                if table_id:
                    link = (
                        session.query(SectionTableRecord)
                        .filter(
                            SectionTableRecord.section_id == section_id,
                            SectionTableRecord.table_id == table_id,
                        )
                        .first()
                    )
                    if link is None:
                        session.add(SectionTableRecord(section_id=section_id, table_id=table_id))

            for element_id in stats.get("figure_ids", []):
                image_id = image_map.get(element_id)
                if image_id:
                    link = (
                        session.query(SectionImageRecord)
                        .filter(
                            SectionImageRecord.section_id == section_id,
                            SectionImageRecord.image_id == image_id,
                        )
                        .first()
                    )
                    if link is None:
                        session.add(SectionImageRecord(section_id=section_id, image_id=image_id))

    def get_paper_by_name(self, paper_name: str) -> Optional[Dict[str, Any]]:
        with self._Session() as session:
            row = (
                session.query(PaperRecord)
                .filter(func.lower(PaperRecord.paper_name) == paper_name.lower())
                .first()
            )
            return self._to_dict(row) if row else None

    def list_papers(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(PaperRecord)
                .order_by(PaperRecord.created_at.desc(), PaperRecord.id.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": int(r.id),
                    "paper_name": r.paper_name,
                    "title": r.title,
                    "abstract": r.abstract,
                    "source_pdf_path": r.source_pdf_path,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    def list_papers_for_user(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(PaperRecord)
                .join(UserPaperRecord, UserPaperRecord.paper_id == PaperRecord.id)
                .filter(UserPaperRecord.user_id == user_id)
                .order_by(UserPaperRecord.created_at.desc(), PaperRecord.id.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": int(r.id),
                    "paper_name": r.paper_name,
                    "title": r.title,
                    "abstract": r.abstract,
                    "source_pdf_path": r.source_pdf_path,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    def create_user(
        self,
        *,
        email: str,
        password_hash: str,
        password_salt: str,
        display_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        email = (email or "").strip().lower()
        if not email:
            return None

        self.ensure_schema()
        with self._Session() as session:
            user = UserRecord(
                email=email,
                display_name=(display_name or "").strip() or None,
                password_hash=password_hash,
                password_salt=password_salt,
            )
            session.add(user)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return None
            session.refresh(user)
            return {
                "id": int(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "password_hash": user.password_hash,
                "password_salt": user.password_salt,
                "created_at": user.created_at,
            }

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        key = (email or "").strip().lower()
        if not key:
            return None
        with self._Session() as session:
            row = (
                session.query(UserRecord)
                .filter(func.lower(UserRecord.email) == key)
                .first()
            )
            if not row:
                return None
            return {
                "id": int(row.id),
                "email": row.email,
                "display_name": row.display_name,
                "password_hash": row.password_hash,
                "password_salt": row.password_salt,
                "created_at": row.created_at,
            }

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._Session() as session:
            row = session.query(UserRecord).filter(UserRecord.id == user_id).first()
            if not row:
                return None
            return {
                "id": int(row.id),
                "email": row.email,
                "display_name": row.display_name,
                "created_at": row.created_at,
            }

    def link_user_to_paper(self, user_id: int, paper_id: int) -> None:
        self.ensure_schema()
        with self._Session() as session:
            link = (
                session.query(UserPaperRecord)
                .filter(
                    UserPaperRecord.user_id == user_id,
                    UserPaperRecord.paper_id == paper_id,
                )
                .first()
            )
            if link is None:
                session.add(UserPaperRecord(user_id=user_id, paper_id=paper_id))
                session.commit()

    def user_has_access_to_paper(self, user_id: int, paper_id: int) -> bool:
        with self._Session() as session:
            row = (
                session.query(UserPaperRecord.id)
                .filter(
                    UserPaperRecord.user_id == user_id,
                    UserPaperRecord.paper_id == paper_id,
                )
                .first()
            )
            return row is not None

    def get_paper_by_id(self, paper_id: int) -> Optional[Dict[str, Any]]:
        with self._Session() as session:
            row = session.query(PaperRecord).filter(PaperRecord.id == paper_id).first()
            return self._to_dict(row) if row else None

    def get_images_for_paper_id(self, paper_id: int) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(ImageRecord)
                .filter(ImageRecord.paper_id == paper_id)
                .order_by(ImageRecord.page_number.asc(), ImageRecord.id.asc())
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def get_references_for_paper_id(self, paper_id: int) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(ReferenceRecord)
                .filter(ReferenceRecord.paper_id == paper_id)
                .order_by(ReferenceRecord.page_number.asc(), ReferenceRecord.id.asc())
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def get_tables_for_paper_id(self, paper_id: int) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(TableDataRecord)
                .filter(TableDataRecord.paper_id == paper_id)
                .order_by(TableDataRecord.page_number.asc(), TableDataRecord.id.asc())
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def get_text_blocks_for_paper_id(self, paper_id: int) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(TextBlockRecord)
                .filter(TextBlockRecord.paper_id == paper_id)
                .order_by(TextBlockRecord.page_number.asc(), TextBlockRecord.id.asc())
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def get_sections_for_paper_id(self, paper_id: int) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(SectionRecord)
                .filter(SectionRecord.paper_id == paper_id)
                .order_by(SectionRecord.section_key.asc())
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def get_section_text_blocks_for_paper_id(self, paper_id: int) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(
                    SectionRecord.id.label("section_id"),
                    SectionRecord.original_name.label("section_name"),
                    TextBlockRecord.id.label("text_block_db_id"),
                    TextBlockRecord.element_id.label("text_block_element_id"),
                    TextBlockRecord.page_number,
                    TextBlockRecord.text_content,
                )
                .join(
                    SectionTextBlockRecord,
                    SectionTextBlockRecord.section_id == SectionRecord.id,
                )
                .join(TextBlockRecord, TextBlockRecord.id == SectionTextBlockRecord.text_block_id)
                .filter(SectionRecord.paper_id == paper_id)
                .order_by(
                    SectionRecord.section_key.asc(),
                    TextBlockRecord.page_number.asc(),
                    TextBlockRecord.id.asc(),
                )
                .all()
            )
            return [dict(r._mapping) for r in rows]

    def get_images_for_paper(self, paper_name: str) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(ImageRecord)
                .join(PaperRecord, PaperRecord.id == ImageRecord.paper_id)
                .filter(func.lower(PaperRecord.paper_name) == paper_name.lower())
                .order_by(ImageRecord.page_number.asc(), ImageRecord.id.asc())
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def get_references_for_paper(self, paper_name: str) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(ReferenceRecord)
                .join(PaperRecord, PaperRecord.id == ReferenceRecord.paper_id)
                .filter(func.lower(PaperRecord.paper_name) == paper_name.lower())
                .order_by(ReferenceRecord.page_number.asc(), ReferenceRecord.id.asc())
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def get_tables_for_paper(self, paper_name: str) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(TableDataRecord)
                .join(PaperRecord, PaperRecord.id == TableDataRecord.paper_id)
                .filter(func.lower(PaperRecord.paper_name) == paper_name.lower())
                .order_by(TableDataRecord.page_number.asc(), TableDataRecord.id.asc())
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def get_text_blocks_for_paper(self, paper_name: str) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(TextBlockRecord)
                .join(PaperRecord, PaperRecord.id == TextBlockRecord.paper_id)
                .filter(func.lower(PaperRecord.paper_name) == paper_name.lower())
                .order_by(TextBlockRecord.page_number.asc(), TextBlockRecord.id.asc())
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def get_sections_for_paper(self, paper_name: str) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(SectionRecord)
                .join(PaperRecord, PaperRecord.id == SectionRecord.paper_id)
                .filter(func.lower(PaperRecord.paper_name) == paper_name.lower())
                .order_by(SectionRecord.section_key.asc())
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def upsert_paper_guide(
        self,
        *,
        paper_id: int,
        document_uuid: Optional[str],
        guide_json: Dict[str, Any],
        guide_plan_json: Optional[Dict[str, Any]] = None,
        guide_file_path: Optional[str] = None,
        guide_plan_file_path: Optional[str] = None,
        question_section_pairs: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        self.ensure_schema()
        with self._Session() as session:
            row = (
                session.query(PaperGuideRecord)
                .filter(PaperGuideRecord.paper_id == paper_id)
                .first()
            )
            if row is None:
                row = PaperGuideRecord(paper_id=paper_id)
                session.add(row)

            row.document_uuid = document_uuid
            row.guide_json = guide_json or {}
            row.guide_plan_json = guide_plan_json or {}
            row.guide_file_path = guide_file_path
            row.guide_plan_file_path = guide_plan_file_path
            row.question_section_pairs_json = question_section_pairs or []
            session.commit()
            session.refresh(row)
            return self._to_dict(row)

    def get_paper_guide_for_paper_id(self, paper_id: int) -> Optional[Dict[str, Any]]:
        with self._Session() as session:
            row = (
                session.query(PaperGuideRecord)
                .filter(PaperGuideRecord.paper_id == paper_id)
                .first()
            )
            return self._to_dict(row) if row else None

    def replace_paper_questions(
        self,
        *,
        paper_id: int,
        document_uuid: Optional[str],
        questions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        self.ensure_schema()
        with self._Session() as session:
            session.query(PaperQuestionRecord).filter(PaperQuestionRecord.paper_id == paper_id).delete()

            created: List[PaperQuestionRecord] = []
            for item in questions or []:
                row = PaperQuestionRecord(
                    paper_id=paper_id,
                    document_uuid=document_uuid,
                    question_text=str(item.get("question_text") or "").strip(),
                    scoped_sections_json=item.get("scoped_sections") or [],
                    retrieval_payload_json=item.get("retrieval_payload") or {},
                    status=str(item.get("status") or "pending"),
                    answer_text=item.get("answer_text"),
                    confidence=item.get("confidence"),
                    error_message=item.get("error_message"),
                )
                if not row.question_text:
                    continue
                session.add(row)
                created.append(row)

            session.commit()
            for row in created:
                session.refresh(row)
            return [self._to_dict(r) for r in created]

    def list_paper_questions_for_paper_id(self, paper_id: int) -> List[Dict[str, Any]]:
        with self._Session() as session:
            rows = (
                session.query(PaperQuestionRecord)
                .filter(PaperQuestionRecord.paper_id == paper_id)
                .order_by(PaperQuestionRecord.id.asc())
                .all()
            )
            return [self._to_dict(r) for r in rows]

    def get_paper_question_for_paper_id(self, paper_id: int, question_id: int) -> Optional[Dict[str, Any]]:
        with self._Session() as session:
            row = (
                session.query(PaperQuestionRecord)
                .filter(
                    PaperQuestionRecord.paper_id == paper_id,
                    PaperQuestionRecord.id == question_id,
                )
                .first()
            )
            return self._to_dict(row) if row else None

    def claim_question_for_generation(
        self,
        *,
        paper_id: int,
        question_id: int,
        force_regenerate: bool = False,
    ) -> Dict[str, Any]:
        with self._Session() as session:
            row = (
                session.query(PaperQuestionRecord)
                .filter(
                    PaperQuestionRecord.paper_id == paper_id,
                    PaperQuestionRecord.id == question_id,
                )
                .with_for_update()
                .first()
            )
            if row is None:
                raise ValueError("question_not_found")

            if row.status == "running":
                raise ValueError("question_running")

            if row.status == "completed" and not force_regenerate and row.answer_text:
                return self._to_dict(row)

            row.status = "running"
            row.error_message = None
            if force_regenerate:
                row.answer_text = None
                row.confidence = None
            session.commit()
            session.refresh(row)
            return self._to_dict(row)

    def complete_paper_question(
        self,
        *,
        paper_id: int,
        question_id: int,
        answer_text: str,
        confidence: Optional[str],
    ) -> Dict[str, Any]:
        with self._Session() as session:
            row = (
                session.query(PaperQuestionRecord)
                .filter(
                    PaperQuestionRecord.paper_id == paper_id,
                    PaperQuestionRecord.id == question_id,
                )
                .with_for_update()
                .first()
            )
            if row is None:
                raise ValueError("question_not_found")

            row.status = "completed"
            row.answer_text = answer_text
            row.confidence = confidence
            row.error_message = None
            session.commit()
            session.refresh(row)
            return self._to_dict(row)

    def fail_paper_question(
        self,
        *,
        paper_id: int,
        question_id: int,
        error_message: str,
    ) -> Dict[str, Any]:
        with self._Session() as session:
            row = (
                session.query(PaperQuestionRecord)
                .filter(
                    PaperQuestionRecord.paper_id == paper_id,
                    PaperQuestionRecord.id == question_id,
                )
                .with_for_update()
                .first()
            )
            if row is None:
                raise ValueError("question_not_found")

            row.status = "failed"
            row.error_message = error_message
            session.commit()
            session.refresh(row)
            return self._to_dict(row)
