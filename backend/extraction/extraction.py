"""
Simplified PDF extraction module.

Handles complete extraction workflow:
1. PDF ingestion (validation, text extraction, OCR)
2. Metadata extraction (title, abstract, sections)
3. Section hierarchy extraction
4. Save required results to output artifacts
5. Generate reading guide via LangGraph workflow
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from backend.extraction.pipelines.ingest_pipeline import IngestPipeline, DeduplicationSkipped
from backend.extraction.pipelines.metadata_pipeline import MetadataExtractionPipeline
from backend.extraction.pipelines.section_hierarchy_pipeline import SectionHierarchyPipeline
from backend.extraction.persistence import PostgresPaperStore
from backend.extraction.app.pdf_loader import PDFLoader, LoaderConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


def _generate_reading_guide(
    title: str,
    abstract: str,
    sections: list[Dict[str, Any]],
    full_text: str,
    defer_answer_generation: bool = True,
    document_id: Optional[str] = None,
    paper_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Generate a reading guide using the LangGraph workflow.
    
    Args:
        title: Paper title
        abstract: Paper abstract
        sections: List of extracted sections
        full_text: Complete paper text
        
    Returns:
        Reading guide dict or None if generation fails
    """
    try:
        logger.info("Generating reading guide via LangGraph workflow...")
        
        result_state = generate_reading_guide_state(
            title=title,
            abstract=abstract,
            sections=sections,
            full_text=full_text,
            defer_answer_generation=defer_answer_generation,
            document_id=document_id,
            paper_id=paper_id,
        )
        
        reading_guide = result_state.get("reading_guide")
        if reading_guide:
            logger.info("✅ Reading guide generated successfully")
            return reading_guide
        else:
            logger.warning("⚠️  Reading guide not generated (workflow completed but no guide in state)")
            return None
            
    except Exception as exc:
        logger.error(f"Failed to generate reading guide: {exc}", exc_info=True)
        return None


def generate_reading_guide_state(
    title: str,
    abstract: str,
    sections: list[Dict[str, Any]],
    full_text: str,
    defer_answer_generation: bool = True,
    skip_retrieve_and_qa: bool = False,
    document_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run LangGraph reading-guide workflow and return the full state payload."""
    # Import here to avoid circular imports and allow optional usage
    _BACKEND_DIR = Path(__file__).resolve().parent.parent
    _PROJECT_ROOT = _BACKEND_DIR.parent
    for _p in (_PROJECT_ROOT, _BACKEND_DIR):
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))

    from rag.graph import get_agent

    agent = get_agent()
    state = {
        "title": title,
        "abstract": abstract,
        "sections": sections,
        "full_text": full_text,
        "errors": [],
        "defer_answer_generation": defer_answer_generation,
        "skip_retrieve_and_qa": skip_retrieve_and_qa,
        "document_id": document_id,
        "indexing_complete": False,
        "chunks": [],
    }
    result_state = agent.invoke(state)
    indexing_skipped = result_state.get("indexing_skipped", False)
    logger.info(f"Graph completed. Indexing skipped: {indexing_skipped}")
    return result_state


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
        loader = PDFLoader(
            LoaderConfig(
                parallel_page_processing=True,
            )
        )
        self.ingest_pipeline = IngestPipeline(loader=loader)
        self.metadata_pipeline = MetadataExtractionPipeline(groq_api_key=groq_api_key)
        self.hierarchy_pipeline = SectionHierarchyPipeline()
        
        logger.info("PDF Extractor initialized")
    
    def extract(
        self, 
        pdf_path: str | Path,
        output_dir: str | Path = "output",
        force_ocr: bool = False,
        save_metadata_file: bool = False,
        save_fulltext_file: bool = False,
        generate_reading_guide: bool = True,
        skip_if_exists: bool = True,
        enable_incremental: bool = True,
        persist_to_db: bool = True,
    ) -> Dict[str, Any]:
        """
        Extract all information from a PDF file.
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Directory to save extracted data (default: output/)
            force_ocr: Force OCR regardless of text density
            save_metadata_file: Persist <document_id>_metadata.json sidecar
            save_fulltext_file: Persist <document_id>_fulltext.txt sidecar
            
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
        _t = time.perf_counter()
        postgres_dsn = _resolve_postgres_dsn() if persist_to_db else None
        ingest_cache_dir = output_dir / "ingest_cache"
        try:
            validated_doc = self.ingest_pipeline.process(
                pdf_path=pdf_path,
                force_ocr=force_ocr,
                skip_if_exists=skip_if_exists,
                postgres_dsn=postgres_dsn,
                cache_dir=ingest_cache_dir,
                enable_incremental=enable_incremental,
            )
        except DeduplicationSkipped as exc:
            logger.info(
                "Skipping extraction for duplicate PDF (hash=%s, paper_id=%s)",
                exc.pdf_hash,
                exc.existing_paper_id,
            )
            return {
                "skipped": True,
                "reason": "duplicate_pdf_hash",
                "existing_paper_id": exc.existing_paper_id,
                "pdf_hash": exc.pdf_hash,
            }
        
        logger.info(f"Step 1/3: Ingestion complete. DoclingDocument cached: {validated_doc.docling_document is not None}")
        logger.info(
            "Extraction: using document_id=%s for pdf=%s",
            validated_doc.document_id,
            pdf_path.name,
        )
        logger.info(
            "Extraction: pdf_hash=%s, document_id=%s",
            validated_doc.pdf_hash,
            validated_doc.document_id,
        )
        logger.info(f"Step 1 complete in {time.perf_counter() - _t:.2f}s")
        
        # Extract full text from validated document
        full_text = validated_doc.full_text
        
        # Step 2: Extract metadata
        logger.info("Step 2/3: Extracting metadata...")
        _t = time.perf_counter()
        processed_doc = self.metadata_pipeline.process(validated_doc)
        logger.info(f"Step 2 complete in {time.perf_counter() - _t:.2f}s")
        
        # Step 3: Extract section hierarchy
        logger.info("Step 3/3: Extracting section hierarchy...")
        _t = time.perf_counter()
        hierarchy = self.hierarchy_pipeline.process_from_processed_document(processed_doc)
        logger.info(f"Step 3 complete in {time.perf_counter() - _t:.2f}s")
        hierarchy_sections = getattr(getattr(hierarchy, "hierarchy", None), "sections", []) or []
        section_count = len(hierarchy_sections)
        if section_count == 0:
            logger.error(
                "Extraction: 0 sections detected for %s. Metadata coverage was likely too low. "
                "Hierarchy saved but indexing will produce 0 chunks. QA will not work for this paper.",
                pdf_path.name,
            )
        else:
            logger.info("Extraction: %d sections detected", section_count)
        
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
        reference_section_id = None
        for section in hierarchy.hierarchy.sections:
            section_title = str(getattr(section, "title", "") or "").strip().lower()
            if "reference" in section_title or "bibliography" in section_title or "works cited" in section_title:
                reference_section_id = getattr(section, "section_id", None)
                break

        references = []
        for block in text_blocks:
            if not isinstance(block, dict):
                continue
            label = str(block.get("label") or "").strip().lower()
            section_name = str(block.get("section_title") or block.get("section") or "").strip().lower()
            if label in {"reference", "bibliography"} or (
                "reference" in section_name or "bibliography" in section_name or "works cited" in section_name
            ):
                if label and label != "reference":
                    block["docling_label"] = label
                block["label"] = "reference"
                block["section_title"] = "Reference"
                block["section"] = "Reference"
                if reference_section_id and not block.get("section_id"):
                    block["section_id"] = reference_section_id

                references.append(
                    {
                        "id": block.get("id"),
                        "page": block.get("page"),
                        "text": block.get("text"),
                        "label": "reference",
                        "section_id": block.get("section_id") or reference_section_id,
                        "section_title": "Reference",
                    }
                )
        extracted_elements["references"] = references
        
        # Build metadata payload (without IDs)
        metadata_dict = {
            "document_id": pdf_path.name,  # Use PDF filename as document_id
            "paper_title": processed_doc.metadata.title,
            "abstract": processed_doc.metadata.abstract,
            "keywords": processed_doc.metadata.keywords,
            "sections": remove_ids_from_sections(full_sections),
            "global_stats": processed_doc.metadata.global_stats.model_dump(mode='json') if processed_doc.metadata.global_stats else {},
            "inference": processed_doc.metadata.inference.model_dump(mode='json') if processed_doc.metadata.inference else {}
        }

        metadata_file: Optional[Path] = None
        if save_metadata_file:
            metadata_file = output_dir / f"{doc_id}_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved metadata: {metadata_file}")
        
        # Save hierarchy
        hierarchy_file = output_dir / f"{doc_id}_hierarchy.json"
        with open(hierarchy_file, 'w', encoding='utf-8') as f:
            json.dump(hierarchy.model_dump(mode='json'), f, indent=2, ensure_ascii=False)
        logger.info(f"Saved hierarchy: {hierarchy_file}")
        
        # Save full text sidecar only when explicitly requested.
        fulltext_file: Optional[Path] = None
        if save_fulltext_file:
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
                "keywords": processed_doc.metadata.keywords,
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
        
        reading_guide: Optional[Dict[str, Any]] = None
        if generate_reading_guide:
            logger.info("Generating reading guide...")
            reading_guide = _generate_reading_guide(
                title=processed_doc.metadata.title or "",
                abstract=processed_doc.metadata.abstract or "",
                sections=[s.model_dump(mode='json', exclude_none=True) for s in processed_doc.metadata.sections],
                full_text=full_text,
                defer_answer_generation=True,
                document_id=doc_id,
                paper_id=None,
            )
            if reading_guide:
                logger.info("✅ Reading guide generated and will be stored with paper")
            else:
                logger.warning("⚠️  Reading guide generation failed, paper will be stored without guide")
        else:
            logger.info("Skipping reading guide generation (deferred)")
        
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
                    reading_guide=reading_guide,
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

        files = {
            "hierarchy": str(hierarchy_file),
            "complete": str(complete_file),
        }
        if metadata_file is not None:
            files["metadata"] = str(metadata_file)
        if fulltext_file is not None:
            files["fulltext"] = str(fulltext_file)
        
        result = {
            "document_id": doc_id,
            "pdf_name": pdf_path.name,
            "metadata": metadata_dict,
            "extracted_elements": extracted_elements,
            "hierarchy": hierarchy.model_dump(mode='json'),
            "full_text": full_text,
            "reading_guide": reading_guide,
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
                **files,
            },
            "database": {
                "enabled": bool(postgres_dsn),
                "stored": db_result.stored if db_result else False,
                "paper_id": db_result.paper_id if db_result else None,
                "paper_name": db_result.paper_name if db_result else None,
                "reason": db_result.reason if db_result else (
                    "persistence_disabled" if not persist_to_db else "postgres_not_configured"
                ),
                "reading_guide_stored": bool(reading_guide) if persist_to_db else False,
            },
        }
        
        logger.info(f"Extraction completed in {extraction_time:.2f}s")
        return result


def extract_pdf(
    pdf_path: str | Path,
    output_dir: str | Path = "output",
    groq_api_key: Optional[str] = None,
    force_ocr: bool = False,
    save_metadata_file: bool = False,
    save_fulltext_file: bool = False,
    generate_reading_guide: bool = True,
    skip_if_exists: bool = True,
    enable_incremental: bool = True,
    persist_to_db: bool = True,
) -> Dict[str, Any]:
    """
    Convenience function for extracting a single PDF.
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save results (default: output/)
        groq_api_key: Groq API key
        force_ocr: Force OCR regardless of text density
        save_metadata_file: Persist <document_id>_metadata.json sidecar
        save_fulltext_file: Persist <document_id>_fulltext.txt sidecar
        
    Returns:
        Extraction results dictionary
    """
    extractor = PDFExtractor(groq_api_key=groq_api_key)
    return extractor.extract(
        pdf_path,
        output_dir,
        force_ocr,
        save_metadata_file,
        save_fulltext_file,
        generate_reading_guide,
        skip_if_exists,
        enable_incremental,
        persist_to_db,
    )


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python extraction.py <pdf_path> [output_dir]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
    
    result = extract_pdf(pdf_path, output_dir)
    print(f"\n✓ Extraction completed!")
    print(f"Document ID: {result['document_id']}")
    print(f"Title: {result['metadata'].get('paper_title', 'N/A')}")
    print(f"Pages: {result['stats']['pages']}")
    print(f"Sections: {result['stats']['sections']}")
    print(f"\nFiles saved to: {output_dir}/")