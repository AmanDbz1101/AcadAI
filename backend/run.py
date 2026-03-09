"""
backend/run.py
==============
Orchestrates the full backend pipeline (extraction → categorization → Q&A/summary).

Pipeline
--------
The unified LangGraph workflow handles everything:
1. **Extraction** – PDF → title, abstract, sections, hierarchy, fulltext
2. **Categorization** – title + abstract → category, confidence, reasoning
3. **Q&A** (if query provided) – query → retrieval → answer
4. **Summarization** (if no query) → structured paper summary

Usage
-----
As a module::

    from backend.run import PaperAnalysisPipeline

    pipeline = PaperAnalysisPipeline()
    
    # Basic extraction + categorization
    result = pipeline.run("path/to/paper.pdf")
    
    # With Q&A
    result = pipeline.run("path/to/paper.pdf", query="What is the main contribution?")

As a CLI script::

    python backend/run.py path/to/paper.pdf
    python backend/run.py path/to/paper.pdf --query "What is the methodology?"
    python backend/run.py path/to/paper.pdf --summarize
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Ensure both the project root and ``backend/`` are on sys.path:
#   - project root  → resolves ``config`` (config.py lives there)
#   - backend/      → resolves ``rag.*`` internal imports inside the rag package
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_DIR.parent
for _p in (_PROJECT_ROOT, _BACKEND_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ---------------------------------------------------------------------------
# Project-level config (GROQ_API_KEY, LOG_LEVEL, …)
# ---------------------------------------------------------------------------
from config import GROQ_API_KEY, LOG_LEVEL  # noqa: E402 – import after path setup

# ---------------------------------------------------------------------------
# RAG unified graph (handles extraction + categorization + Q&A/summary)
# ---------------------------------------------------------------------------
# Import directly to avoid path conflicts
if "rag" not in sys.modules:
    import rag.graph
    import rag.states

from rag.graph import get_agent  # noqa: E402
from rag.states import AgentState  # noqa: E402

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------

class PaperAnalysisPipeline:
    """
    End-to-end pipeline: PDF → extraction → categorization → Q&A/summary.
    
    The unified LangGraph workflow handles all steps automatically.

    Parameters
    ----------
    groq_api_key:
        Groq API key used for LLM calls. Falls back to the value in ``config.py``
        (which reads ``$GROQ_API_KEY`` from the environment).
    enable_db:
        When *True*, persist rich Docling-extracted data (text blocks with
        bounding boxes, section hierarchy, tables, figures, formulas) to the
        local PostgreSQL database after each pipeline run.  Defaults to *False*
        so existing behaviour is unchanged.
    database_url:
        Explicit PostgreSQL DSN.  Falls back to the ``DATABASE_URL`` env var,
        then individual ``PG_*`` env vars, then ``localhost/research_papers``.
    """

    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        enable_db: bool = False,
        database_url: Optional[str] = None,
    ) -> None:
        self.groq_api_key = groq_api_key or GROQ_API_KEY
        
        # Set API key in environment for graph nodes to use
        if self.groq_api_key:
            import os
            os.environ["GROQ_API_KEY"] = self.groq_api_key

        logger.info("Initializing unified workflow graph...")
        self._graph = get_agent()

        # Optional DB ingestion
        self._db_pipeline = None
        if enable_db:
            try:
                from backend.extraction.pipelines.db_ingestion_pipeline import DBIngestionPipeline
                from backend.database.connection import DatabaseConnection
                db_conn = DatabaseConnection(database_url) if database_url else DatabaseConnection()
                self._db_pipeline = DBIngestionPipeline(db_connection=db_conn)
                logger.info("DB ingestion pipeline ready.")
            except Exception as exc:
                logger.warning("DB ingestion pipeline could not be initialised: %s", exc)

        logger.info("PaperAnalysisPipeline ready.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        pdf_path: str | Path,
        force_ocr: bool = False,
        query: Optional[str] = None,
        summarize: bool = False,
        store_in_db: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the full pipeline on a single PDF.

        Parameters
        ----------
        pdf_path:
            Path to the PDF file to process.
        force_ocr:
            Pass ``True`` to force OCR even when selectable text is present.
        query:
            Optional user question for Q&A mode. If provided, triggers
            retrieval → answer workflow instead of summarization.
        summarize:
            If True and no query provided, generate a structured summary.
            Default behavior when neither query nor summarize is specified.
        store_in_db:
            If *True*, persist rich Docling data (text blocks, sections,
            tables, figures, formulas with bounding boxes) to PostgreSQL.
            Requires ``enable_db=True`` when constructing the pipeline.

        Returns
        -------
        dict with keys from AgentState:

        ``document_id``         – UUID assigned to the document
        ``title``               – Paper title
        ``abstract``            – Paper abstract
        ``category``            – Paper category classification
        ``confidence``          – Classification confidence
        ``category_reasoning``  – Explanation for category choice
        ``answer``              – (if query provided) Answer to query
        ``summary``             – (if summarize mode) Paper summary
        ``errors``              – List of any errors encountered
        ``db_document_id``      – (if store_in_db) ID of the DB record
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Prepare initial state
        initial_state = {
            "pdf_path": str(pdf_path),
            "force_ocr": force_ocr,
            "query": query,
            "errors": [],
        }

        logger.info(f"Running pipeline for: {pdf_path.name}")
        if query:
            logger.info(f"  Mode: Q&A - '{query}'")
        else:
            logger.info(f"  Mode: Extraction + Categorization + Summary")

        # Run the unified graph
        try:
            result_state = self._graph.invoke(initial_state)
        except Exception as exc:
            logger.error(f"Pipeline failed: {exc}")
            raise

        # Convert to clean dict
        result = dict(result_state)
        
        # Add convenience fields for backward compatibility
        result["pdf_name"] = pdf_path.name
        
        # Log summary
        category = result.get("category", "UNKNOWN")
        confidence = result.get("confidence", "UNKNOWN")
        logger.info(f"Pipeline complete – category={category}, confidence={confidence}")
        
        if result.get("errors"):
            logger.warning(f"Errors encountered: {result['errors']}")

        # --- Optional DB ingestion ---
        if store_in_db:
            document_id = result.get("document_id")
            if self._db_pipeline is None:
                logger.warning(
                    "store_in_db=True but DB pipeline not initialised. "
                    "Construct PaperAnalysisPipeline with enable_db=True."
                )
            elif document_id:
                try:
                    db_doc_id = self._db_pipeline.ingest(
                        pdf_path=pdf_path,
                        document_id=document_id,
                    )
                    result["db_document_id"] = db_doc_id
                    logger.info("Document stored in DB: %s", db_doc_id)
                except Exception as exc:
                    logger.error("DB ingestion failed: %s", exc)
                    result.setdefault("errors", []).append(f"DB ingestion failed: {exc}")

        return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python backend/run.py",
        description="Run the Research Paper Assistant pipeline (extraction → categorization → Q&A/summary).",
    )
    parser.add_argument("pdf_path", help="Path to the PDF file to process.")
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Force OCR even when selectable text is present.",
    )
    parser.add_argument(
        "--query",
        default=None,
        metavar="QUESTION",
        help="Ask a question about the paper (enables Q&A mode).",
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Generate a structured summary of the paper.",
    )
    parser.add_argument(
        "--groq-api-key",
        default=None,
        metavar="KEY",
        help="Groq API key. Falls back to $GROQ_API_KEY environment variable.",
    )
    parser.add_argument(
        "--store-in-db",
        action="store_true",
        help=(
            "Persist rich Docling data (text blocks with bounding boxes, sections, "
            "tables, figures, formulas) to local PostgreSQL after extraction. "
            "Set DATABASE_URL or PG_* env vars for connection details."
        ),
    )
    parser.add_argument(
        "--database-url",
        default=None,
        metavar="DSN",
        help="PostgreSQL DSN (overrides DATABASE_URL env var).",
    )
    parser.add_argument(
        "--no-full-text",
        action="store_true",
        help="Omit the full_text field from printed output (can be very long).",
    )
    return parser


def _print_result(result: Dict[str, Any], hide_full_text: bool = False) -> None:
    display = {k: v for k, v in result.items() if not (hide_full_text and k == "full_text")}
    print(json.dumps(display, indent=2, ensure_ascii=False, default=str))


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    pipeline = PaperAnalysisPipeline(
        groq_api_key=args.groq_api_key,
        enable_db=args.store_in_db,
        database_url=args.database_url if hasattr(args, "database_url") else None,
    )

    result = pipeline.run(
        pdf_path=args.pdf_path,
        force_ocr=args.force_ocr,
        query=args.query,
        summarize=args.summarize,
        store_in_db=args.store_in_db,
    )

    print("\n" + "=" * 70)
    print("  RESEARCH PAPER ASSISTANT - PIPELINE RESULT")
    print("=" * 70)
    print(f"  Document ID : {result.get('document_id', 'N/A')}")
    print(f"  PDF         : {result.get('pdf_name', 'N/A')}")
    print(f"  Title       : {result.get('title', 'N/A')[:70]}")
    print()
    print(f"  Category    : {result.get('category', 'N/A')}")
    print(f"  Confidence  : {result.get('confidence', 'N/A')}")
    print(f"  Reasoning   : {result.get('category_reasoning', 'N/A')[:100]}")
    
    # Q&A output
    if args.query and result.get('answer'):
        print()
        print("  " + "-" * 66)
        print("  Q&A RESULT")
        print("  " + "-" * 66)
        print(f"  Query       : {args.query}")
        print(f"  Answer      :")
        for line in result['answer'].split('\n')[:10]:  # First 10 lines
            print(f"    {line}")
    
    # Summary output
    if result.get('summary'):
        print()
        print("  " + "-" * 66)
        print("  SUMMARY")
        print("  " + "-" * 66)
        for line in result['summary'].split('\n')[:15]:  # First 15 lines
            print(f"    {line}")
    
    # Errors
    errors = result.get("errors", [])
    if errors:
        print()
        print(f"  ⚠  Errors   : {errors}")
    
    print("=" * 70)

    # File artifacts
    saved = result.get("extraction_files", {})
    if saved:
        print("\nArtifacts saved:")
        for label, path in saved.items():
            print(f"  {label:12s}: {path}")
    print()


if __name__ == "__main__":
    main()
