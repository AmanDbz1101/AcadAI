"""
PostgreSQL persistence for extracted paper artifacts.

Stores one paper record per unique paper name (case-insensitive), and links
sections, text blocks, tables, and images to that paper for later retrieval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except ImportError:  # pragma: no cover - dependency is optional unless DB is enabled
    psycopg2 = None
    Json = None
    RealDictCursor = None


logger = logging.getLogger(__name__)


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
        self.dsn = dsn

    def _connect(self):
        if psycopg2 is None:
            raise RuntimeError(
                "psycopg2 is not installed. Install 'psycopg2-binary' to enable PostgreSQL persistence."
            )
        return psycopg2.connect(self.dsn)

    def ensure_schema(self) -> None:
        """Create required tables and indexes if they do not exist."""
        ddl = """
        CREATE TABLE IF NOT EXISTS papers (
            id BIGSERIAL PRIMARY KEY,
            paper_name TEXT NOT NULL,
            title TEXT,
            abstract TEXT,
            pdf_hash TEXT,
            source_pdf_path TEXT,
            document_uuid TEXT,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE UNIQUE INDEX IF NOT EXISTS uq_papers_name_lower ON papers ((lower(paper_name)));
        CREATE UNIQUE INDEX IF NOT EXISTS uq_papers_pdf_hash ON papers (pdf_hash) WHERE pdf_hash IS NOT NULL;

        CREATE TABLE IF NOT EXISTS sections (
            id BIGSERIAL PRIMARY KEY,
            paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            section_key TEXT NOT NULL,
            parent_section_id BIGINT REFERENCES sections(id) ON DELETE SET NULL,
            original_name TEXT NOT NULL,
            level INTEGER NOT NULL,
            page_start INTEGER NOT NULL,
            position INTEGER NOT NULL,
            stats_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(paper_id, section_key)
        );

        CREATE INDEX IF NOT EXISTS idx_sections_paper_id ON sections(paper_id);

        CREATE TABLE IF NOT EXISTS text_blocks (
            id BIGSERIAL PRIMARY KEY,
            paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            element_id TEXT NOT NULL,
            page_number INTEGER,
            text_content TEXT,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(paper_id, element_id)
        );

        CREATE INDEX IF NOT EXISTS idx_text_blocks_paper_id ON text_blocks(paper_id);

        CREATE TABLE IF NOT EXISTS tables_data (
            id BIGSERIAL PRIMARY KEY,
            paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            element_id TEXT NOT NULL,
            page_number INTEGER,
            markdown_content TEXT,
            text_content TEXT,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(paper_id, element_id)
        );

        CREATE INDEX IF NOT EXISTS idx_tables_data_paper_id ON tables_data(paper_id);

        CREATE TABLE IF NOT EXISTS images (
            id BIGSERIAL PRIMARY KEY,
            paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
            element_id TEXT NOT NULL,
            page_number INTEGER,
            image_path TEXT,
            caption TEXT,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(paper_id, element_id)
        );

        CREATE INDEX IF NOT EXISTS idx_images_paper_id ON images(paper_id);

        CREATE TABLE IF NOT EXISTS section_text_blocks (
            section_id BIGINT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
            text_block_id BIGINT NOT NULL REFERENCES text_blocks(id) ON DELETE CASCADE,
            PRIMARY KEY(section_id, text_block_id)
        );

        CREATE TABLE IF NOT EXISTS section_tables (
            section_id BIGINT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
            table_id BIGINT NOT NULL REFERENCES tables_data(id) ON DELETE CASCADE,
            PRIMARY KEY(section_id, table_id)
        );

        CREATE TABLE IF NOT EXISTS section_images (
            section_id BIGINT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
            image_id BIGINT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
            PRIMARY KEY(section_id, image_id)
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()

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

        with self._connect() as conn:
            with conn.cursor() as cur:
                existing_id, reason = self._find_existing_paper(cur, paper_name, pdf_hash)
                if existing_id is not None:
                    return PersistResult(False, existing_id, paper_name, reason)

                cur.execute(
                    """
                    INSERT INTO papers (paper_name, title, abstract, pdf_hash, source_pdf_path, document_uuid, metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        paper_name,
                        title,
                        abstract,
                        pdf_hash,
                        source_pdf_path,
                        document_uuid,
                        Json(metadata_json),
                    ),
                )
                paper_id = cur.fetchone()[0]

                section_db_map = self._insert_sections(cur, paper_id, sections)
                text_map = self._insert_text_blocks(cur, paper_id, extracted_elements.get("text_blocks", []))
                table_map = self._insert_tables(cur, paper_id, extracted_elements.get("tables", []))
                image_map = self._insert_images(cur, paper_id, extracted_elements.get("figures", []))

                self._link_section_elements(cur, section_db_map, text_map, table_map, image_map)

            conn.commit()

        return PersistResult(True, paper_id, paper_name, "stored")

    def _find_existing_paper(self, cur, paper_name: str, pdf_hash: Optional[str]) -> Tuple[Optional[int], str]:
        if pdf_hash:
            cur.execute("SELECT id FROM papers WHERE pdf_hash = %s LIMIT 1", (pdf_hash,))
            row = cur.fetchone()
            if row:
                return row[0], "duplicate_pdf_hash"

        cur.execute("SELECT id FROM papers WHERE lower(paper_name) = lower(%s) LIMIT 1", (paper_name,))
        row = cur.fetchone()
        if row:
            return row[0], "duplicate_paper_name"

        return None, ""

    def _insert_sections(self, cur, paper_id: int, sections: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        section_map: Dict[str, Dict[str, Any]] = {}

        def _walk(nodes: List[Dict[str, Any]], parent_db_id: Optional[int], base_key: str) -> None:
            for idx, section in enumerate(nodes):
                section_key = f"{base_key}.{idx}"
                stats = section.get("stats") or {}

                cur.execute(
                    """
                    INSERT INTO sections (
                        paper_id, section_key, parent_section_id, original_name,
                        level, page_start, position, stats_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        paper_id,
                        section_key,
                        parent_db_id,
                        section.get("original_name") or "Untitled",
                        int(section.get("level") or 1),
                        int(section.get("page_start") or 1),
                        idx,
                        Json(stats),
                    ),
                )
                section_id = cur.fetchone()[0]

                section_map[section_key] = {
                    "id": section_id,
                    "stats": stats,
                }

                children = section.get("sections") or []
                if children:
                    _walk(children, section_id, section_key)

        _walk(sections or [], None, "s")
        return section_map

    def _insert_text_blocks(self, cur, paper_id: int, text_blocks: List[Dict[str, Any]]) -> Dict[str, int]:
        mapping: Dict[str, int] = {}
        for block in text_blocks:
            element_id = block.get("id")
            if not element_id:
                continue

            cur.execute(
                """
                INSERT INTO text_blocks (paper_id, element_id, page_number, text_content, metadata_json)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (paper_id, element_id) DO UPDATE
                SET page_number = EXCLUDED.page_number,
                    text_content = EXCLUDED.text_content,
                    metadata_json = EXCLUDED.metadata_json
                RETURNING id
                """,
                (
                    paper_id,
                    element_id,
                    block.get("page"),
                    block.get("text"),
                    Json(block),
                ),
            )
            mapping[element_id] = cur.fetchone()[0]
        return mapping

    def _insert_tables(self, cur, paper_id: int, tables: List[Dict[str, Any]]) -> Dict[str, int]:
        mapping: Dict[str, int] = {}
        for table in tables:
            element_id = table.get("id")
            if not element_id:
                continue

            cur.execute(
                """
                INSERT INTO tables_data (paper_id, element_id, page_number, markdown_content, text_content, metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (paper_id, element_id) DO UPDATE
                SET page_number = EXCLUDED.page_number,
                    markdown_content = EXCLUDED.markdown_content,
                    text_content = EXCLUDED.text_content,
                    metadata_json = EXCLUDED.metadata_json
                RETURNING id
                """,
                (
                    paper_id,
                    element_id,
                    table.get("page"),
                    table.get("markdown"),
                    table.get("text"),
                    Json(table),
                ),
            )
            mapping[element_id] = cur.fetchone()[0]
        return mapping

    def _insert_images(self, cur, paper_id: int, images: List[Dict[str, Any]]) -> Dict[str, int]:
        mapping: Dict[str, int] = {}
        for image in images:
            element_id = image.get("id")
            if not element_id:
                continue

            cur.execute(
                """
                INSERT INTO images (paper_id, element_id, page_number, image_path, caption, metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (paper_id, element_id) DO UPDATE
                SET page_number = EXCLUDED.page_number,
                    image_path = EXCLUDED.image_path,
                    caption = EXCLUDED.caption,
                    metadata_json = EXCLUDED.metadata_json
                RETURNING id
                """,
                (
                    paper_id,
                    element_id,
                    image.get("page"),
                    image.get("image_path"),
                    image.get("caption"),
                    Json(image),
                ),
            )
            mapping[element_id] = cur.fetchone()[0]
        return mapping

    def _link_section_elements(
        self,
        cur,
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
                    cur.execute(
                        """
                        INSERT INTO section_text_blocks (section_id, text_block_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (section_id, text_id),
                    )

            for element_id in stats.get("table_ids", []):
                table_id = table_map.get(element_id)
                if table_id:
                    cur.execute(
                        """
                        INSERT INTO section_tables (section_id, table_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (section_id, table_id),
                    )

            for element_id in stats.get("figure_ids", []):
                image_id = image_map.get(element_id)
                if image_id:
                    cur.execute(
                        """
                        INSERT INTO section_images (section_id, image_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (section_id, image_id),
                    )

    def get_paper_by_name(self, paper_name: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM papers
                    WHERE lower(paper_name) = lower(%s)
                    LIMIT 1
                    """,
                    (paper_name,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def get_images_for_paper(self, paper_name: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT i.*
                    FROM images i
                    JOIN papers p ON p.id = i.paper_id
                    WHERE lower(p.paper_name) = lower(%s)
                    ORDER BY i.page_number ASC, i.id ASC
                    """,
                    (paper_name,),
                )
                return [dict(r) for r in cur.fetchall()]

    def get_tables_for_paper(self, paper_name: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT t.*
                    FROM tables_data t
                    JOIN papers p ON p.id = t.paper_id
                    WHERE lower(p.paper_name) = lower(%s)
                    ORDER BY t.page_number ASC, t.id ASC
                    """,
                    (paper_name,),
                )
                return [dict(r) for r in cur.fetchall()]

    def get_text_blocks_for_paper(self, paper_name: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT tb.*
                    FROM text_blocks tb
                    JOIN papers p ON p.id = tb.paper_id
                    WHERE lower(p.paper_name) = lower(%s)
                    ORDER BY tb.page_number ASC, tb.id ASC
                    """,
                    (paper_name,),
                )
                return [dict(r) for r in cur.fetchall()]

    def get_sections_for_paper(self, paper_name: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT s.*
                    FROM sections s
                    JOIN papers p ON p.id = s.paper_id
                    WHERE lower(p.paper_name) = lower(%s)
                    ORDER BY s.section_key ASC
                    """,
                    (paper_name,),
                )
                return [dict(r) for r in cur.fetchall()]
