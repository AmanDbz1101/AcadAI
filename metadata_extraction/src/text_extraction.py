"""
Text extraction from PDF using unstructured library.

This module handles PDF parsing and text block extraction with metadata.
"""

from typing import Any
from dataclasses import dataclass
from unstructured.partition.pdf import partition_pdf


@dataclass
class TextBlock:
    """Represents a text block extracted from PDF.
    
    Attributes:
        text: The text content
        page_number: Page number (1-indexed)
        element_type: Type of element (e.g., 'Title', 'NarrativeText')
        metadata: Additional metadata (font size, coordinates, etc.)
    """
    text: str
    page_number: int
    element_type: str
    metadata: dict[str, Any]


class PDFTextExtractor:
    """Extracts structured text blocks from PDF documents."""
    
    def __init__(self, pdf_path: str):
        """Initialize extractor with PDF path.
        
        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = pdf_path
        self._elements = None
    
    def extract(self) -> list[TextBlock]:
        """Extract all text blocks from the PDF.
        
        Returns:
            List of TextBlock objects with text and metadata
            
        Raises:
            FileNotFoundError: If PDF file doesn't exist
            Exception: For PDF parsing errors
        """
        try:
            # Use unstructured to partition the PDF
            # strategy="hi_res" gives better layout analysis
            # infer_table_structure helps with structured content
            elements = partition_pdf(
                filename=self.pdf_path,
                strategy="hi_res",
                infer_table_structure=True,
                coordinates = True
            )
            
            self._elements = elements
            
            # Convert to TextBlock objects
            text_blocks = []
            for element in elements:
                # Get page number (default to 1 if not available)
                page_num = getattr(
                    element.metadata,
                    'page_number',
                    1
                )
                
                # Extract metadata (exclude non-serializable objects like coordinates)
                metadata = {}
                if hasattr(element.metadata, 'detection_class_prob'):
                    metadata['confidence'] = element.metadata.detection_class_prob
                
                # Create text block
                block = TextBlock(
                    text=str(element),
                    page_number=page_num,
                    element_type=element.category,
                    metadata=metadata
                )
                text_blocks.append(block)
            
            return text_blocks
            
        except FileNotFoundError:
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")
        except Exception as e:
            raise Exception(f"Error extracting text from PDF: {str(e)}")
    
    def get_full_text(self) -> str:
        """Get complete text content of the PDF.
        
        Returns:
            Concatenated text from all blocks
        """
        blocks = self.extract()
        return "\n\n".join(block.text for block in blocks)
