"""
Unit tests for PDF validation module.

Tests the PDFValidator class and validation logic.
"""

import hashlib
from pathlib import Path

import pytest

from backend.app.ingestion.validation import (
    PDFValidator,
    ValidationResult,
    ValidationError,
    ValidationErrorType,
)


class TestPDFValidator:
    """Test suite for PDFValidator."""
    
    def test_validator_initialization_defaults(self):
        """Test validator initialization with default parameters."""
        validator = PDFValidator()
        
        assert validator.max_file_size_bytes == 50 * 1024 * 1024
        assert validator.allowed_extensions == {'.pdf'}
        assert validator.min_pages == 1
        assert validator.max_pages is None
    
    def test_validator_initialization_custom(self):
        """Test validator initialization with custom parameters."""
        validator = PDFValidator(
            max_file_size_mb=100,
            allowed_extensions={'.pdf', '.PDF'},
            min_pages=2,
            max_pages=500,
        )
        
        assert validator.max_file_size_bytes == 100 * 1024 * 1024
        assert validator.allowed_extensions == {'.pdf', '.PDF'}
        assert validator.min_pages == 2
        assert validator.max_pages == 500
    
    def test_validate_valid_pdf(self, sample_pdf_path):
        """Test validation of a valid PDF file."""
        validator = PDFValidator()
        result = validator.validate(sample_pdf_path)
        
        assert result.is_valid is True
        assert result.pdf_path == sample_pdf_path
        assert result.page_count >= 1
        assert result.file_size_bytes > 0
        assert result.pdf_hash is not None
        assert len(result.pdf_hash) == 64  # SHA256 hash length
        assert len(result.errors) == 0
    
    def test_validate_file_not_found(self, tmp_path):
        """Test validation with non-existent file."""
        validator = PDFValidator()
        non_existent = tmp_path / "does_not_exist.pdf"
        
        result = validator.validate(non_existent)
        
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert result.errors[0].error_type == ValidationErrorType.FILE_NOT_FOUND
    
    def test_validate_wrong_extension(self, non_pdf_path):
        """Test validation with wrong file extension."""
        validator = PDFValidator()
        result = validator.validate(non_pdf_path)
        
        assert result.is_valid is False
        assert any(
            error.error_type == ValidationErrorType.INVALID_EXTENSION 
            for error in result.errors
        )
    
    def test_validate_corrupted_pdf(self, corrupted_pdf_path):
        """Test validation with corrupted PDF."""
        validator = PDFValidator()
        result = validator.validate(corrupted_pdf_path)
        
        assert result.is_valid is False
        assert any(
            error.error_type in [ValidationErrorType.CORRUPTED_FILE, ValidationErrorType.INVALID_FORMAT]
            for error in result.errors
        )
    
    def test_validate_empty_pdf(self, empty_pdf_path):
        """Test validation with PDF that has minimal content."""
        validator = PDFValidator(min_pages=1)
        result = validator.validate(empty_pdf_path)
        
        # Should be valid if it has at least one page
        assert result.is_valid is True
        assert result.page_count >= 1
    
    def test_validate_encrypted_pdf(self, encrypted_pdf_path):
        """Test validation with encrypted PDF."""
        validator = PDFValidator()
        result = validator.validate(encrypted_pdf_path)
        
        assert result.is_valid is False
        assert any(
            error.error_type == ValidationErrorType.ENCRYPTED 
            for error in result.errors
        )
    
    def test_validate_file_too_large(self, sample_pdf_path):
        """Test validation with file size constraint."""
        # Set very small size limit
        validator = PDFValidator(max_file_size_mb=0.001)
        result = validator.validate(sample_pdf_path)
        
        assert result.is_valid is False
        assert any(
            error.error_type == ValidationErrorType.FILE_TOO_LARGE 
            for error in result.errors
        )
    
    def test_validate_min_pages_constraint(self, sample_pdf_path):
        """Test validation with minimum pages constraint."""
        validator = PDFValidator(min_pages=100)
        result = validator.validate(sample_pdf_path)
        
        # Should fail if PDF has fewer than 100 pages
        if result.page_count and result.page_count < 100:
            assert result.is_valid is False
    
    def test_validate_max_pages_constraint(self, large_pdf_path):
        """Test validation with maximum pages constraint."""
        validator = PDFValidator(max_pages=2)
        result = validator.validate(large_pdf_path)
        
        # Should fail if PDF has more than 2 pages
        if result.page_count and result.page_count > 2:
            assert result.is_valid is False
    
    def test_hash_consistency(self, sample_pdf_path):
        """Test that the same file produces the same hash."""
        validator = PDFValidator()
        
        result1 = validator.validate(sample_pdf_path)
        result2 = validator.validate(sample_pdf_path)
        
        assert result1.pdf_hash == result2.pdf_hash
    
    def test_hash_uniqueness(self, sample_pdf_path, large_pdf_path):
        """Test that different files produce different hashes."""
        validator = PDFValidator()
        
        result1 = validator.validate(sample_pdf_path)
        result2 = validator.validate(large_pdf_path)
        
        assert result1.pdf_hash != result2.pdf_hash
    
    def test_validation_result_attributes(self, sample_pdf_path):
        """Test that validation result contains all expected attributes."""
        validator = PDFValidator()
        result = validator.validate(sample_pdf_path)
        
        assert hasattr(result, 'is_valid')
        assert hasattr(result, 'pdf_path')
        assert hasattr(result, 'pdf_hash')
        assert hasattr(result, 'page_count')
        assert hasattr(result, 'file_size_bytes')
        assert hasattr(result, 'errors')
        assert isinstance(result.errors, list)


class TestValidationError:
    """Test suite for ValidationError dataclass."""
    
    def test_validation_error_creation(self):
        """Test creating a ValidationError."""
        error = ValidationError(
            error_type=ValidationErrorType.FILE_TOO_LARGE,
            message="File exceeds maximum size",
            details="Maximum: 50MB, Actual: 75MB"
        )
        
        assert error.error_type == ValidationErrorType.FILE_TOO_LARGE
        assert error.message == "File exceeds maximum size"
        assert error.details == "Maximum: 50MB, Actual: 75MB"
    
    def test_validation_error_without_details(self):
        """Test creating a ValidationError without details."""
        error = ValidationError(
            error_type=ValidationErrorType.FILE_NOT_FOUND,
            message="File not found"
        )
        
        assert error.error_type == ValidationErrorType.FILE_NOT_FOUND
        assert error.details is None


class TestValidationResult:
    """Test suite for ValidationResult dataclass."""
    
    def test_validation_result_creation(self, sample_pdf_path):
        """Test creating a ValidationResult."""
        result = ValidationResult(
            is_valid=True,
            pdf_path=sample_pdf_path,
            pdf_hash="abc123",
            page_count=5,
            file_size_bytes=1024,
        )
        
        assert result.is_valid is True
        assert result.pdf_path == sample_pdf_path
        assert result.pdf_hash == "abc123"
        assert result.page_count == 5
        assert result.file_size_bytes == 1024
        assert result.errors == []
    
    def test_validation_result_with_errors(self, sample_pdf_path):
        """Test ValidationResult with errors."""
        errors = [
            ValidationError(
                error_type=ValidationErrorType.FILE_TOO_LARGE,
                message="File too large"
            )
        ]
        
        result = ValidationResult(
            is_valid=False,
            pdf_path=sample_pdf_path,
            errors=errors,
        )
        
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].error_type == ValidationErrorType.FILE_TOO_LARGE
