"""
PDF validation module.

Validates PDF files before processing to ensure:
- File integrity (not corrupted)
- Readable format
- Size constraints
- Page count requirements
"""

import hashlib
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum

import pymupdf  # PyMuPDF for PDF validation


class ValidationErrorType(str, Enum):
    """Types of validation errors."""
    FILE_NOT_FOUND = "file_not_found"
    INVALID_FORMAT = "invalid_format"
    CORRUPTED_FILE = "corrupted_file"
    FILE_TOO_LARGE = "file_too_large"
    NO_PAGES = "no_pages"
    ENCRYPTED = "encrypted"
    INVALID_EXTENSION = "invalid_extension"


@dataclass
class ValidationError:
    """Validation error details."""
    error_type: ValidationErrorType
    message: str
    details: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of PDF validation."""
    is_valid: bool
    pdf_path: Path
    pdf_hash: Optional[str] = None
    page_count: Optional[int] = None
    file_size_bytes: Optional[int] = None
    errors: List[ValidationError] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class PDFValidator:
    """
    Validates PDF files before ingestion.
    
    Performs comprehensive checks including:
    - File existence and readability
    - PDF format validity
    - File size constraints
    - Page count verification
    - Encryption detection
    """
    
    def __init__(
        self,
        max_file_size_mb: int = 50,
        allowed_extensions: set = None,
        min_pages: int = 1,
        max_pages: Optional[int] = None,
    ):
        """
        Initialize validator with constraints.
        
        Args:
            max_file_size_mb: Maximum allowed file size in MB
            allowed_extensions: Set of allowed file extensions (default: {'.pdf'})
            min_pages: Minimum required page count
            max_pages: Maximum allowed page count (None = unlimited)
        """
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.allowed_extensions = allowed_extensions or {'.pdf'}
        self.min_pages = min_pages
        self.max_pages = max_pages
    
    def validate(self, pdf_path: Path) -> ValidationResult:
        """
        Perform comprehensive PDF validation.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            ValidationResult with status and details
        """
        errors: List[ValidationError] = []
        pdf_hash = None
        page_count = None
        file_size_bytes = None
        
        # Convert to Path if string
        if isinstance(pdf_path, str):
            pdf_path = Path(pdf_path)
        
        # 1. Check file existence
        if not pdf_path.exists():
            errors.append(ValidationError(
                error_type=ValidationErrorType.FILE_NOT_FOUND,
                message=f"File not found: {pdf_path}",
                details=str(pdf_path)
            ))
            return ValidationResult(
                is_valid=False,
                pdf_path=pdf_path,
                errors=errors
            )
        
        # 2. Check file extension
        if pdf_path.suffix.lower() not in self.allowed_extensions:
            errors.append(ValidationError(
                error_type=ValidationErrorType.INVALID_EXTENSION,
                message=f"Invalid file extension: {pdf_path.suffix}",
                details=f"Allowed extensions: {', '.join(self.allowed_extensions)}"
            ))
        
        # 3. Check file size
        try:
            file_size_bytes = pdf_path.stat().st_size
            if file_size_bytes > self.max_file_size_bytes:
                errors.append(ValidationError(
                    error_type=ValidationErrorType.FILE_TOO_LARGE,
                    message=f"File size exceeds limit",
                    details=f"Size: {file_size_bytes / (1024*1024):.2f}MB, Limit: {self.max_file_size_bytes / (1024*1024):.0f}MB"
                ))
        except Exception as e:
            errors.append(ValidationError(
                error_type=ValidationErrorType.INVALID_FORMAT,
                message="Cannot read file size",
                details=str(e)
            ))
        
        # 4. Calculate file hash (for deduplication)
        try:
            pdf_hash = self._calculate_hash(pdf_path)
        except Exception as e:
            errors.append(ValidationError(
                error_type=ValidationErrorType.INVALID_FORMAT,
                message="Cannot calculate file hash",
                details=str(e)
            ))
        
        # 5. Open PDF and validate structure
        try:
            doc = pymupdf.open(pdf_path)
            
            # Check encryption
            if doc.is_encrypted:
                errors.append(ValidationError(
                    error_type=ValidationErrorType.ENCRYPTED,
                    message="PDF is encrypted",
                    details="Password-protected PDFs are not supported"
                ))
                doc.close()
                return ValidationResult(
                    is_valid=False,
                    pdf_path=pdf_path,
                    pdf_hash=pdf_hash,
                    file_size_bytes=file_size_bytes,
                    errors=errors
                )
            
            # Check page count
            page_count = len(doc)
            if page_count < self.min_pages:
                errors.append(ValidationError(
                    error_type=ValidationErrorType.NO_PAGES,
                    message=f"PDF has too few pages",
                    details=f"Pages: {page_count}, Minimum: {self.min_pages}"
                ))
            
            if self.max_pages and page_count > self.max_pages:
                errors.append(ValidationError(
                    error_type=ValidationErrorType.NO_PAGES,
                    message=f"PDF has too many pages",
                    details=f"Pages: {page_count}, Maximum: {self.max_pages}"
                ))
            
            # Verify basic metadata availability
            metadata = doc.metadata
            if metadata is None:
                # Not an error, but note it
                pass
            
            doc.close()
            
        except pymupdf.FileDataError as e:
            errors.append(ValidationError(
                error_type=ValidationErrorType.CORRUPTED_FILE,
                message="PDF file is corrupted or invalid",
                details=str(e)
            ))
        except Exception as e:
            errors.append(ValidationError(
                error_type=ValidationErrorType.INVALID_FORMAT,
                message="Cannot open PDF file",
                details=str(e)
            ))
        
        # Build result
        is_valid = len(errors) == 0
        
        return ValidationResult(
            is_valid=is_valid,
            pdf_path=pdf_path,
            pdf_hash=pdf_hash,
            page_count=page_count,
            file_size_bytes=file_size_bytes,
            errors=errors
        )
    
    def _calculate_hash(self, pdf_path: Path) -> str:
        """
        Calculate SHA256 hash of PDF file.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Hexadecimal hash string
        """
        sha256_hash = hashlib.sha256()
        with open(pdf_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def quick_check(self, pdf_path: Path) -> bool:
        """
        Quick validation check (existence + extension only).
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            True if basic checks pass
        """
        if isinstance(pdf_path, str):
            pdf_path = Path(pdf_path)
        
        return (
            pdf_path.exists() and
            pdf_path.suffix.lower() in self.allowed_extensions
        )
