"""
PDF loader with docling integration.

Loads PDF files and extracts text with layout signals using docling.
Detects machine-readability and determines if OCR is needed.
"""

import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling_core.types.doc import DoclingDocument, DocItem

from backend.models.document import (
    PageContent,
    LayoutSignals,
    BoundingBox,
    FontInfo,
)


@dataclass
class LoaderConfig:
    """Configuration for PDF loader."""
    do_ocr: bool = False  # Enable OCR for scanned PDFs
    extract_images: bool = True
    extract_tables: bool = True
    ocr_engine: str = "easyocr"  # "easyocr" or "tesseract"
    generate_page_images: bool = False
    generate_picture_images: bool = False
    timeout_seconds: int = 120


class PDFLoader:
    """
    Loads PDF files using docling and extracts structured content.
    
    Features:
    - Automatic text extraction with layout preservation
    - Machine-readability detection
    - Optional OCR for scanned documents
    - Bounding box and font signal extraction
    - Reading order preservation
    """
    
    def __init__(self, config: Optional[LoaderConfig] = None):
        """
        Initialize PDF loader.
        
        Args:
            config: Loader configuration (uses defaults if None)
        """
        self.config = config or LoaderConfig()
        self._initialize_converter()
    
    def _initialize_converter(self):
        """Initialize docling converter with pipeline options."""
        # Configure pipeline options
        pipeline_options = PdfPipelineOptions(
            do_ocr=self.config.do_ocr,
            do_table_structure=self.config.extract_tables,
            images_scale=1.0,
            generate_page_images=self.config.generate_page_images,
            generate_picture_images=self.config.generate_picture_images,
        )
        
        # Create converter with options
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options
                )
            }
        )
    
    def load(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Load PDF and extract content with layout signals.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dictionary containing:
                - pages: List of PageContent objects
                - full_text: Concatenated text
                - metadata: Document metadata
                - processing_time: Time taken in seconds
        """
        start_time = time.time()
        
        # Convert PDF
        result = self.converter.convert(pdf_path)
        doc: DoclingDocument = result.document
        
        # Extract pages with layout information
        pages = self._extract_pages(doc)
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Build result
        return {
            "pages": pages,
            "full_text": "\n\n".join(page.text for page in pages),
            "metadata": self._extract_metadata(doc),
            "page_count": len(pages),
            "processing_time": processing_time,
        }
    
    def _extract_pages(self, doc: DoclingDocument) -> List[PageContent]:
        """
        Extract page-wise content with layout signals.
        
        Args:
            doc: Docling document
            
        Returns:
            List of PageContent objects
        """
        pages_dict: Dict[int, List[str]] = {}
        pages_metadata: Dict[int, Dict[str, Any]] = {}
        
        # Group items by page
        for item, level in doc.iterate_items():
            if hasattr(item, 'prov') and item.prov:
                for prov in item.prov:
                    page_no = prov.page_no + 1  # Convert to 1-indexed
                    
                    # Initialize page if needed
                    if page_no not in pages_dict:
                        pages_dict[page_no] = []
                        pages_metadata[page_no] = {
                            'has_images': False,
                            'has_tables': False,
                            'has_formulas': False,
                        }
                    
                    # Extract text
                    text = self._get_item_text(item)
                    if text:
                        pages_dict[page_no].append(text)
                    
                    # Track element types
                    if hasattr(item, 'label'):
                        label = item.label.lower() if item.label else ""
                        if 'picture' in label or 'figure' in label:
                            pages_metadata[page_no]['has_images'] = True
                        elif 'table' in label:
                            pages_metadata[page_no]['has_tables'] = True
                        elif 'formula' in label or 'equation' in label:
                            pages_metadata[page_no]['has_formulas'] = True
        
        # Build PageContent objects
        pages = []
        for page_no in sorted(pages_dict.keys()):
            text = "\n".join(pages_dict[page_no])
            metadata = pages_metadata[page_no]
            
            page_content = PageContent(
                page_number=page_no,
                text=text,
                word_count=len(text.split()),
                char_count=len(text),
                has_images=metadata['has_images'],
                has_tables=metadata['has_tables'],
                has_formulas=metadata['has_formulas'],
            )
            pages.append(page_content)
        
        return pages
    
    def _get_item_text(self, item: DocItem) -> str:
        """
        Extract text from a document item.
        
        Args:
            item: Document item
            
        Returns:
            Extracted text
        """
        if hasattr(item, 'text') and item.text:
            return item.text
        elif hasattr(item, 'export_to_markdown'):
            return item.export_to_markdown()
        return ""
    
    def _extract_metadata(self, doc: DoclingDocument) -> Dict[str, Any]:
        """
        Extract document metadata.
        
        Args:
            doc: Docling document
            
        Returns:
            Metadata dictionary
        """
        metadata = {}
        
        # Try to extract title
        if hasattr(doc, 'name') and doc.name:
            metadata['title'] = doc.name
        
        # Extract other available metadata
        if hasattr(doc, 'origin'):
            metadata['origin'] = doc.origin
        
        return metadata
    
    def detect_readability(self, pages: List[PageContent]) -> Dict[str, Any]:
        """
        Detect if PDF is machine-readable or needs OCR.
        
        Args:
            pages: List of PageContent objects
            
        Returns:
            Dictionary with readability analysis:
                - is_machine_readable: bool
                - average_text_density: float
                - low_density_pages: List[int]
                - recommendation: str
        """
        if not pages:
            return {
                "is_machine_readable": False,
                "average_text_density": 0,
                "low_density_pages": [],
                "recommendation": "No pages found"
            }
        
        # Calculate text density per page (chars per page)
        densities = [page.char_count for page in pages]
        average_density = sum(densities) / len(densities)
        
        # Threshold: < 50 chars per page suggests scanned/image content
        OCR_THRESHOLD = 50
        low_density_pages = [
            page.page_number 
            for page in pages 
            if page.char_count < OCR_THRESHOLD
        ]
        
        is_machine_readable = average_density >= OCR_THRESHOLD
        
        # Generate recommendation
        if is_machine_readable:
            recommendation = "Digital PDF - no OCR needed"
        elif len(low_density_pages) == len(pages):
            recommendation = "Fully scanned PDF - OCR required for all pages"
        else:
            recommendation = f"Hybrid PDF - OCR needed for {len(low_density_pages)} pages"
        
        return {
            "is_machine_readable": is_machine_readable,
            "average_text_density": average_density,
            "low_density_pages": low_density_pages,
            "recommendation": recommendation,
            "total_pages": len(pages),
            "pages_needing_ocr": len(low_density_pages),
        }
    
    def reload_with_ocr(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Reload PDF with OCR enabled.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Same format as load() but with OCR applied
        """
        # Create new config with OCR enabled
        ocr_config = LoaderConfig(
            do_ocr=True,
            extract_images=self.config.extract_images,
            extract_tables=self.config.extract_tables,
            ocr_engine=self.config.ocr_engine,
            timeout_seconds=self.config.timeout_seconds,
        )
        
        # Create new loader with OCR enabled
        ocr_loader = PDFLoader(config=ocr_config)
        
        # Load with OCR
        return ocr_loader.load(pdf_path)
