"""
Simplified PDF extraction module.

Handles complete extraction workflow:
1. PDF ingestion (validation, text extraction, OCR)
2. Metadata extraction (title, abstract, sections)
3. Section hierarchy extraction
4. Save results to input/ folder
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, Union
from datetime import datetime

from backend.extraction.pipelines.ingest_pipeline import IngestPipeline
from backend.extraction.pipelines.metadata_pipeline import MetadataExtractionPipeline
from backend.extraction.pipelines.section_hierarchy_pipeline import SectionHierarchyPipeline
from backend.extraction.persistence import PostgresPaperStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _split_reference_entries(text: str) -> list[str]:
    """Split a references blob into individual entries when delimiters are present."""
    value = (text or "").strip()
    if not value:
        return []

    para_chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", value) if chunk.strip()]
    if len(para_chunks) >= 2:
        first = re.sub(r"^\s*(references|bibliography|works cited)\s*:?\s*", "", para_chunks[0], flags=re.I).strip()
        if first:
            para_chunks[0] = first
        return [chunk for chunk in para_chunks if chunk]

    numbered_chunks = [chunk.strip() for chunk in re.split(r"(?=\n\s*\[?\d+\]?\s+)", value) if chunk.strip()]
    if len(numbered_chunks) >= 2:
        return numbered_chunks

    return [value]


def _extract_references_from_full_text(full_text: str) -> list[dict[str, Any]]:
    """Fallback extraction when element labels/sections do not mark references explicitly."""
    text = (full_text or "").strip()
    if not text:
        return []

    match = re.search(r"\b(references|bibliography|works cited)\b", text, flags=re.I)
    if not match:
        return []

    tail = text[match.start():].strip()
    entries = _split_reference_entries(tail)

    refs: list[dict[str, Any]] = []
    for idx, entry in enumerate(entries):
        value = (entry or "").strip()
        if not value:
            continue
        refs.append(
            {
                "id": f"fulltext_ref_{idx}",
                "page": None,
                "text": value,
                "label": "reference",
                "section_id": None,
                "section_title": "References",
            }
        )

    return refs


def _resolve_postgres_dsn() -> Optional[str]:
    """Resolve PostgreSQL DSN from environment variables."""
    explicit = os.getenv("POSTGRES_DSN")
    if explicit:
        return explicit

    host = os.getenv("POSTGRES_HOST") or os.getenv("PGHOST")
    port = os.getenv("POSTGRES_PORT") or os.getenv("PGPORT")
    dbname = os.getenv("POSTGRES_DB") or os.getenv("PGDATABASE")
    user = os.getenv("POSTGRES_USER") or os.getenv("PGUSER")
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("PGPASSWORD")

    if not all([host, port, dbname, user]):
        return None

    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

    return f"postgresql://{user}@{host}:{port}/{dbname}"


class PDFExtractor:
    """
    Simplified PDF extraction orchestrator.
    
    Combines all extraction pipelines into a single easy-to-use interface.
    """
    
    def __init__(self, groq_api_key: Optional[str] = None):
        """
        Initialize PDF extractor.
        
        Args:
            groq_api_key: Groq API key for LLM-based extraction
        """
        self.ingest_pipeline = IngestPipeline()
        self.metadata_pipeline = MetadataExtractionPipeline(groq_api_key=groq_api_key)
        self.hierarchy_pipeline = SectionHierarchyPipeline()
        
        logger.info("PDF Extractor initialized")
    
    def extract(
        self, 
        pdf_path: Union[str, Path],
        output_dir: Union[str, Path] = "input",
        force_ocr: bool = False
    ) -> Dict[str, Any]:
        """
        Extract all information from a PDF file.
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Directory to save extracted data (default: input/)
            force_ocr: Force OCR regardless of text density
            
        Returns:
            Dictionary containing:
            - document_id: Unique document identifier
            - metadata: Extracted metadata (title, abstract, sections)
            - hierarchy: Section hierarchy
            - full_text: Complete document text
            - stats: Extraction statistics (pages, formulas, tables, figures)
            - files: Paths to saved files
        """
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Starting extraction for: {pdf_path.name}")
        start_time = datetime.now()
        
        # Step 1: Ingest PDF (validation + text extraction + OCR)
        logger.info("Step 1/3: Ingesting PDF...")
        validated_doc = self.ingest_pipeline.process(
            pdf_path=pdf_path,
            force_ocr=force_ocr
        )
        
        # Store full text for later use
        full_text = validated_doc.full_text
        
        # Step 2: Extract metadata
        logger.info("Step 2/3: Extracting metadata...")
        processed_doc = self.metadata_pipeline.process(validated_doc)
        
        # Step 3: Extract section hierarchy
        logger.info("Step 3/3: Extracting section hierarchy...")
        hierarchy = self.hierarchy_pipeline.process_from_processed_document(processed_doc)
        
        # Prepare result
        doc_id = str(processed_doc.document_id)
        
        # Helper function to remove ID fields from sections
        def remove_ids_from_sections(sections_data):
            """Remove ID fields from section stats recursively."""
            cleaned_sections = []
            for section in sections_data:
                section_copy = section.copy() if isinstance(section, dict) else section.model_dump(mode='json', exclude_none=True)
                
                # Remove ID fields from stats if present
                if 'stats' in section_copy and section_copy['stats']:
                    stats = section_copy['stats']
                    stats.pop('formula_ids', None)
                    stats.pop('table_ids', None)
                    stats.pop('figure_ids', None)
                    stats.pop('text_block_ids', None)
                
                # Recursively handle nested sections
                if 'sections' in section_copy and section_copy['sections']:
                    section_copy['sections'] = remove_ids_from_sections(section_copy['sections'])
                
                cleaned_sections.append(section_copy)
            return cleaned_sections
        
        # Prepare full sections with IDs (for complete file)
        full_sections = [s.model_dump(mode='json', exclude_none=True) for s in processed_doc.metadata.sections]

        # Normalize extracted elements and split references/bibliography explicitly.
        extracted_elements = dict(processed_doc.metadata.extracted_elements or {})
        text_blocks = extracted_elements.get("text_blocks") or []
        references = []
        for block in text_blocks:
            if not isinstance(block, dict):
                continue
            label = str(block.get("label") or "").strip().lower()
            section_name = str(block.get("section_title") or block.get("section") or "").strip().lower()
            if (
                label in {"reference", "bibliography"}
                or (
                    "reference" in section_name
                    or "bibliography" in section_name
                    or "works cited" in section_name
                )
                or re.match(r"^\s*(references|bibliography|works cited)\b", str(block.get("text") or ""), flags=re.I)
            ):
                references.append(
                    {
                        "id": block.get("id"),
                        "page": block.get("page"),
                        "text": block.get("text"),
                        "label": label,
                        "section_id": block.get("section_id"),
                        "section_title": block.get("section_title"),
                    }
                )
        if not references:
            references = _extract_references_from_full_text(full_text)
        extracted_elements["references"] = references
        
        # Save metadata (without IDs)
        metadata_file = output_dir / f"{doc_id}_metadata.json"
        metadata_dict = {
            "document_id": pdf_path.name,  # Use PDF filename as document_id
            "paper_title": processed_doc.metadata.title,
            "abstract": processed_doc.metadata.abstract,
            "sections": remove_ids_from_sections(full_sections),
            "global_stats": processed_doc.metadata.global_stats.model_dump(mode='json') if processed_doc.metadata.global_stats else {},
            "inference": processed_doc.metadata.inference.model_dump(mode='json') if processed_doc.metadata.inference else {}
        }
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved metadata: {metadata_file}")
        
        # Save hierarchy
        hierarchy_file = output_dir / f"{doc_id}_hierarchy.json"
        with open(hierarchy_file, 'w', encoding='utf-8') as f:
            json.dump(hierarchy.model_dump(mode='json'), f, indent=2, ensure_ascii=False)
        logger.info(f"Saved hierarchy: {hierarchy_file}")
        
        # Save full text
        fulltext_file = output_dir / f"{doc_id}_fulltext.txt"
        with open(fulltext_file, 'w', encoding='utf-8') as f:
            f.write(full_text)
        logger.info(f"Saved full text: {fulltext_file}")
        
        # Save complete processed document (with IDs preserved)
        complete_file = output_dir / f"{doc_id}_complete.json"
        complete_dict = {
            "document_id": doc_id,
            "metadata": {
                "document_id": pdf_path.name,
                "paper_title": processed_doc.metadata.title,
                "abstract": processed_doc.metadata.abstract,
                "sections": full_sections,  # Keep IDs in complete file
                "global_stats": processed_doc.metadata.global_stats.model_dump(mode='json') if processed_doc.metadata.global_stats else {},
                "inference": processed_doc.metadata.inference.model_dump(mode='json') if processed_doc.metadata.inference else {}
            },
            "extracted_elements": extracted_elements,
        }
        with open(complete_file, 'w', encoding='utf-8') as f:
            json.dump(complete_dict, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved complete document: {complete_file}")

        # Persist to PostgreSQL when configured.
        db_result = None
        postgres_dsn = _resolve_postgres_dsn()
        if postgres_dsn:
            try:
                store = PostgresPaperStore(postgres_dsn)
                section_payload = [s.model_dump(mode='json', exclude_none=True) for s in processed_doc.metadata.sections]
                paper_name = (processed_doc.metadata.title or pdf_path.stem or pdf_path.name).strip()

                db_result = store.persist_extraction(
                    paper_name=paper_name,
                    title=processed_doc.metadata.title,
                    abstract=processed_doc.metadata.abstract,
                    pdf_hash=validated_doc.pdf_hash,
                    source_pdf_path=str(pdf_path),
                    document_uuid=doc_id,
                    metadata_json=metadata_dict,
                    sections=section_payload,
                    extracted_elements=extracted_elements,
                )

                if db_result.stored:
                    logger.info(
                        "Persisted extraction to PostgreSQL (paper_id=%s, paper_name=%s)",
                        db_result.paper_id,
                        db_result.paper_name,
                    )
                else:
                    logger.info(
                        "Skipped PostgreSQL persistence for duplicate paper (paper_id=%s, reason=%s)",
                        db_result.paper_id,
                        db_result.reason,
                    )
            except Exception as exc:
                logger.warning("PostgreSQL persistence failed: %s", exc)
        
        extraction_time = (datetime.now() - start_time).total_seconds()
        
        result = {
            "document_id": doc_id,
            "pdf_name": pdf_path.name,
            "metadata": metadata_dict,
            "extracted_elements": extracted_elements,
            "hierarchy": hierarchy.model_dump(mode='json'),
            "full_text": full_text,
            "stats": {
                "pages": processed_doc.metadata.global_stats.total_pages if processed_doc.metadata.global_stats else 0,
                "sections": processed_doc.metadata.global_stats.total_sections if processed_doc.metadata.global_stats else 0,
                "formulas": processed_doc.metadata.global_stats.total_formulas if processed_doc.metadata.global_stats else 0,
                "tables": processed_doc.metadata.global_stats.total_tables if processed_doc.metadata.global_stats else 0,
                "figures": processed_doc.metadata.global_stats.total_figures if processed_doc.metadata.global_stats else 0,
                "text_blocks": processed_doc.metadata.global_stats.total_text_blocks if processed_doc.metadata.global_stats else 0,
                "extraction_time_seconds": extraction_time
            },
            "files": {
                "metadata": str(metadata_file),
                "hierarchy": str(hierarchy_file),
                "fulltext": str(fulltext_file),
                "complete": str(complete_file)
            },
            "database": {
                "enabled": bool(postgres_dsn),
                "stored": db_result.stored if db_result else False,
                "paper_id": db_result.paper_id if db_result else None,
                "paper_name": db_result.paper_name if db_result else None,
                "reason": db_result.reason if db_result else "postgres_not_configured",
            },
        }
        
        logger.info(f"Extraction completed in {extraction_time:.2f}s")
        return result


def extract_pdf(
    pdf_path: Union[str, Path],
    output_dir: Union[str, Path] = "input",
    groq_api_key: Optional[str] = None,
    force_ocr: bool = False
) -> Dict[str, Any]:
    """
    Convenience function for extracting a single PDF.
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save results (default: input/)
        groq_api_key: Groq API key
        force_ocr: Force OCR regardless of text density
        
    Returns:
        Extraction results dictionary
    """
    extractor = PDFExtractor(groq_api_key=groq_api_key)
    return extractor.extract(pdf_path, output_dir, force_ocr)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python extraction.py <pdf_path> [output_dir]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "input"
    
    result = extract_pdf(pdf_path, output_dir)
    print(f"\n✓ Extraction completed!")
    print(f"Document ID: {result['document_id']}")
    print(f"Title: {result['metadata'].get('paper_title', 'N/A')}")
    print(f"Pages: {result['stats']['pages']}")
    print(f"Sections: {result['stats']['sections']}")
    print(f"\nFiles saved to: {output_dir}/")
