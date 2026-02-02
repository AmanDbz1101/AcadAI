"""
Fast document extraction using Docling library
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
from docling.document_converter import DocumentConverter


class DoclingExtractor:
    """Fast markdown extraction using Docling"""
    
    def __init__(self):
        self.converter = DocumentConverter()
    
    def extract_markdown(self, pdf_path: str) -> str:
        """
        Extract markdown from PDF using Docling
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Markdown text
        """
        result = self.converter.convert(pdf_path)
        doc = result.document
        markdown = doc.export_to_markdown()
        return markdown
    
    def extract_structured_data(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract structured document data using Docling
        
        Returns:
            Dict with markdown, headings, stats, and page count
        """
        result = self.converter.convert(pdf_path)
        doc = result.document
        
        # Extract markdown
        markdown = doc.export_to_markdown()
        
        # Extract all headings with levels
        headings = []
        for item, level in doc.iterate_items():
            if item.label == "section_header":
                headings.append({
                    "text": item.text,
                    "level": level,
                    "page": getattr(item.prov[0], "page_no", 1) if item.prov else 1
                })
        
        # Count document elements
        element_counts = {
            "formulas": 0,
            "tables": 0,
            "pictures": 0,
            "code_blocks": 0,
            "text_blocks": 0,
            "list_items": 0,
            "captions": 0
        }
        
        for item, level in doc.iterate_items():
            if item.label in ["formula", "equation"]:
                element_counts["formulas"] += 1
            elif item.label == "table":
                element_counts["tables"] += 1
            elif item.label == "picture":
                element_counts["pictures"] += 1
            elif item.label == "code":
                element_counts["code_blocks"] += 1
            elif item.label == "text":
                element_counts["text_blocks"] += 1
            elif item.label == "list_item":
                element_counts["list_items"] += 1
            elif item.label == "caption":
                element_counts["captions"] += 1
        
        # Get total pages
        total_pages = self._count_pages_from_doc(doc)
        
        return {
            "markdown": markdown,
            "headings": headings,
            "element_counts": element_counts,
            "total_pages": total_pages
        }
    
    def _count_pages_from_doc(self, doc) -> int:
        """Count total pages from document"""
        max_page = 0
        for item, _ in doc.iterate_items():
            if item.prov:
                page_no = getattr(item.prov[0], "page_no", 0)
                max_page = max(max_page, page_no)
        return max(max_page, 1)
    
    def extract_abstract_from_markdown(self, markdown: str) -> str:
        """
        Extract abstract from markdown text using pattern matching
        
        Args:
            markdown: Full markdown text
            
        Returns:
            Abstract text or empty string
        """
        # Try to find abstract section
        abstract_pattern = r'(?i)(?:^|\n)#{1,3}\s*abstract\s*\n((?:(?!^#{1,3}\s).)+)'
        match = re.search(abstract_pattern, markdown, re.MULTILINE | re.DOTALL)
        
        if match:
            abstract = match.group(1).strip()
            # Clean up the abstract
            abstract = re.sub(r'\n+', ' ', abstract)
            abstract = re.sub(r'\s+', ' ', abstract)
            return abstract
        
        # Fallback: try to find text after "Abstract" keyword
        lines = markdown.split('\n')
        abstract_lines = []
        capture = False
        
        for line in lines:
            line_lower = line.lower().strip()
            
            if 'abstract' in line_lower and len(line_lower) < 50:
                capture = True
                continue
            
            if capture:
                # Stop at next heading or introduction
                if line.startswith('#') or 'introduction' in line.lower():
                    break
                if line.strip():
                    abstract_lines.append(line.strip())
        
        if abstract_lines:
            return ' '.join(abstract_lines)
        
        return ""
    
    def count_latex_formulas(self, markdown: str) -> int:
        """Count LaTeX formulas in markdown"""
        # Count inline math $...$
        inline = len(re.findall(r'\$[^$]+\$', markdown))
        # Count display math $$...$$
        display = len(re.findall(r'\$\$[^$]+\$\$', markdown))
        return inline + display
    
    def count_tables(self, markdown: str) -> int:
        """Count markdown tables"""
        # Look for table delimiter pattern |---|---|
        tables = re.findall(r'\|[\s\-:]+\|', markdown)
        return len(tables)
    
    def count_figures(self, markdown: str) -> int:
        """Count figure references in markdown"""
        # Match "Figure N", "Fig. N", "Fig N"
        figures = re.findall(r'(?i)\b(?:figure|fig\.?)\s+\d+', markdown)
        # Deduplicate
        unique_figures = set(figures)
        return len(unique_figures)
